from rest_framework.views import APIView
from django.shortcuts import render
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse, Http404, JsonResponse
from usermanagement.utils import RequestValidator
from django.contrib.auth.models import User
import json
import logging
import pprint
import os
import string
from django.core.servers.basehttp import FileWrapper
import re
from collections import Counter

#Imports from user defined modules
from models import Topology, Fabric, FabricRuleDB, DeployedFabricStats
from fabric_rule import generate_fabric_rules, delete_fabric_rules
from serializer.topology_serializer import TopologyGetSerializer, TopologySerializer, TopologyGetDetailSerializer, TopologyPutSerializer
from serializer.fabric_serializer import FabricSerializer, FabricGetSerializer, FabricGetDetailSerializer, FabricPutSerializer
from serializer.fabric_serializer import FabricRuleDBGetSerializer
from serializer.deployed_serializer import DeployedFabricGetSerializer, DeployedFabricDetailGetSerializer
from configuration.models import Configuration
from discoveryrule.models import DiscoveryRule
from fabric.const import INVALID, LOG_SEARCH_COL
from discoveryrule.models import DiscoveryRule

logger = logging.getLogger(__name__)

SYSLOG_FILE = "/var/log/syslog"

# Create your views here.
class JSONResponse(HttpResponse):
    """
    An HttpResponse that renders its content into JSON.
    """

    def __init__(self, data, **kwargs):
        content = JSONRenderer().render(data)
        kwargs['content_type'] = 'application/json'
        super(JSONResponse, self).__init__(content, **kwargs)

class TopologyList(APIView):
    """
    Fetch Topology List or Add a new entry to Topology
    """
    def dispatch(self,request, *args, **kwargs):
        me = RequestValidator(request.META)
        if me.user_is_exist():
            return super(TopologyList, self).dispatch(request,*args, **kwargs)
        else:
            resp = me.invalid_token()
            return JsonResponse(resp,status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, format=None):
        topology_list = Topology.objects.filter(status = True).order_by('name')
        serializer = TopologyGetSerializer(topology_list, many=True)
        index = 0
        for item in serializer.data:
            try:
                item['user_name'] = User.objects.get(id=topology_list[index].user_id).username
            except User.DoesNotExist:
                raise Http404
            index = index + 1
        return Response(serializer.data)

    def post(self, request, format=None):
        serializer = TopologySerializer(data=request.data)
        me = RequestValidator(request.META)
        if serializer.is_valid():
            topology_obj = Topology()
            topology_obj.user_id = me.user_is_exist().user_id
            topology_obj.name = request.data['name']
            topology_obj.submit = request.data['submit']
            topology_obj.topology_json = json.dumps(request.data['topology_json'])
            try:
                topology_obj.config_json = json.dumps(request.data['config_json'])
            except:
                topology_obj.config_json = json.dumps([])
            try:
                topology_obj.defaults = json.dumps(request.data['defaults'])
            except:
                topology_obj.defaults = json.dumps({})
            topology_obj.save()
            serializer = TopologyGetSerializer(topology_obj)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TopologyDetail(APIView):
    """
    Retrieve, update or delete a Topology instance.
    """
    def dispatch(self,request, *args, **kwargs):
        me = RequestValidator(request.META)
        if me.user_is_exist():
            return super(TopologyDetail, self).dispatch(request,*args, **kwargs)
        else:
            resp = me.invalid_token()
            return JsonResponse(resp,status=status.HTTP_400_BAD_REQUEST)

    def get_object(self, id):
        try:
            return Topology.objects.get(pk=id)
        except Topology.DoesNotExist:
            raise Http404

    def get(self, request, id, format=None):
        topology = self.get_object(id)
        serializer = TopologyGetDetailSerializer(topology)
        topo_detail = serializer.data
        topo_detail['topology_json'] = json.loads(topo_detail['topology_json'])
        try:
            topo_detail['config_json'] = json.loads(topo_detail['config_json'])
        except:
            topo_detail['config_json'] = []
        try:
            topo_detail['defaults'] = json.loads(topo_detail['defaults'])
        except:
            topo_detail['defaults'] = {}
        return Response(topo_detail)

    def put(self, request, id, format=None):
        topology = self.get_object(id)
        if request.data['name'] == self.get_object(id).name:
            serializer = TopologyPutSerializer(data=request.data)
        else:
            serializer = TopologySerializer(data=request.data)
        me = RequestValidator(request.META)
        if serializer.is_valid():
            count = Fabric.objects.filter(topology = topology).count()
            if count:
                logger.error("Fail to update Topology id " + str(id) + ", Number of Fabrics using it as base topology-" + str(count))
            else:
                topology_obj = topology
                topology_obj.user_id = me.user_is_exist().user_id
                topology_obj.name = request.data['name']
                topology_obj.submit = request.data['submit']
                topology_obj.topology_json = json.dumps(request.data['topology_json'])
                try:
                    topology_obj.config_json = json.dumps(request.data['config_json'])
                except:
                    topology_obj.config_json = json.dumps([])
                try:
                    topology_obj.defaults = json.dumps(request.data['defaults'])
                except:
                    topology_obj.defaults =json.dumps({})
                topology_obj.save()
                serailizer = TopologyGetDetailSerializer(topology_obj)
                resp = serailizer.data
                resp['topology_json'] = json.loads(resp['topology_json'])
                try:
                    resp['config_json'] = json.loads(resp['config_json'])
                except:
                    resp['config_json'] = []
                try:
                    resp['defaults'] = json.loads(resp['defaults'])
                except:
                    resp['defaults'] = {}
                return Response(resp)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id, format=None):
        topology = self.get_object(id)
        count = Fabric.objects.filter(topology = topology).count()
        if count:
            logger.error("Fail to delete Topology id " + str(id) + ", " +\
            str(count) + " Fabrics are using it as base topology")
            return Response("Topology is in use", status=status.HTTP_400_BAD_REQUEST)
        topology.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FabricList(APIView):
    """
    Fetch Fabric List or Add a new entry to Fabric
    """
    def dispatch(self,request, *args, **kwargs):
        me = RequestValidator(request.META)
        if me.user_is_exist():
            return super(FabricList, self).dispatch(request,*args, **kwargs)
        else:
            resp = me.invalid_token()
            return JsonResponse(resp,status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, format=None):
        fabric_list = Fabric.objects.filter(status = True).order_by('id')
        serializer = FabricGetSerializer(fabric_list, many=True)
        index = 0
        for item in serializer.data:
            item['topology_name'] = fabric_list[index].topology.name
            item['topology_id']  = fabric_list[index].topology.id
            try:
                item['user_name']   = User.objects.get(id=fabric_list[index].user_id).username
            except User.DoesNotExist:
                raise Http404
            index = index + 1
        return Response(serializer.data)

    def post(self, request, format=None):
        
        success = True
        resp = {}
        resp['Error'] = ' '
        serializer = FabricSerializer(data=request.data)
        topology = Topology.objects.get(id=request.data['topology_id'])
        topology_json = json.loads(topology.topology_json)
        me = RequestValidator(request.META)
        if serializer.is_valid():
            if request.data['instance'] < 1:
                logger.error("Fabric Instances cannot be less than 1")
            else:
                fabric_obj = Fabric()
                fabric_obj.name = request.data['name']
                fabric_obj.user_id = me.user_is_exist().user_id
                fabric_obj.topology = topology
                topology.used += 1
                topology.save()
                fabric_obj.instance = request.data['instance']
                fabric_obj.validate = request.data['validate']
                fabric_obj.locked = request.data['locked']
                fabric_obj.config_json = json.dumps(request.data['config_json'])
                for config in request.data['config_json']:
                    config_obj = Configuration.objects.get(id = config['configuration_id'])
                    config_obj.used += 1
                    config_obj.save()
                fabric_obj.submit = request.data['submit']
                try:
                    fabric_obj.system_id = json.dumps(request.data['system_id'])
                except:
                    fabric_obj.system_id = []
                try:
                    fabric_obj.save()
                except:
                    logger.error("Failed to create Fabric: " + fabric_obj.name)
                    resp['Error'] = 'Failed to create Fabric' 
                    return JsonResponse(resp,status=status.HTTP_400_BAD_REQUEST)
                                
                # filling discovery rule with system_id
                try:
                    sys_id_obj = json.loads(fabric_obj.system_id)
                    config_obj = json.loads(fabric_obj.config_json)
                    regex  =  fabric_obj.name + "(_)([1-9][0-9]*)(_)([a-zA-Z]*-[1-9])"
                    for switch_systemId_info in sys_id_obj:
                        if not success:
                            break
                        switch_name = (re.search(regex, switch_systemId_info['name'])).group(4)
                        replica_num = int((re.search(regex, switch_systemId_info['name'])).group(2))
                        system_id = switch_systemId_info['system_id']
                        for config in config_obj:
                            if switch_name == config['name']:
                                discoveryrule_name = 'serial_'+switch_systemId_info['system_id']
                                old_dis_rule = DiscoveryRule.objects.filter(name= discoveryrule_name)
                                if old_dis_rule:
                                    obj = DiscoveryRule.objects.get(name= discoveryrule_name)
                                    logger.error("DIscovery Rule existed with system id: "+switch_systemId_info\
                                                 ['system_id']+" wiht switch_name: "+obj.switch_name)
                                    if obj.fabric_id == fabric_obj.id:
                                        resp['Error'] = 'Serial id: '+switch_systemId_info['system_id']+\
                                                        ' is repeated in this Fabric'
                                    else:
                                        resp['Error'] = "serial id: "+switch_systemId_info['system_id']+\
                                                        " is existed with switch: "+obj.switch_name
                                    logger.error(resp['Error'])
                                    success = False
                                    break
                                
                                dis_rule_obj = DiscoveryRule()
                                dis_rule_obj.priority = 100
                                dis_rule_obj.name = discoveryrule_name
                                dis_rule_obj.config_id = config['configuration_id']
                                dis_rule_obj.match = 'serial_id'
                                dis_rule_obj.subrules = [system_id]
                                dis_rule_obj.fabric_id = fabric_obj.id
                                dis_rule_obj.replica_num = replica_num
                                dis_rule_obj.switch_name = switch_systemId_info['name']
                                dis_rule_obj.save()
                except:
                    success = False
                    logger.error('Failed to update discoveryRule DB with system_id rule for fabric_id: '+\
                                 str(fabric_obj.id))
                    resp['Error'] = 'Failed to update DiscoveryRule DB' 
                
                if success:   
                    if (generate_fabric_rules(request.data['name'],\
                    request.data['instance'], fabric_obj, request.data['config_json'],\
                    topology_json)):
                        serializer = FabricGetSerializer(fabric_obj)
                        logger.info("Successfully created Fabric id: " + str(fabric_obj.id))
                        return Response(serializer.data, status=status.HTTP_201_CREATED)
                    else:
                        success = False
                        logger.error("Failed to update FabricRuleDb: " + fabric_obj.name)
                        resp['Error'] = 'Failed to update FabricRule DB'
                    
                if not success:
                    try:
                        DiscoveryRule.objects.filter(fabric_id = fabric_obj.id).delete()
                    except:
                        pass
                    Fabric.objects.filter(id = fabric_obj.id).delete()
                    logger.error("Failed to create Fabric: " + fabric_obj.name)
                    return JsonResponse(resp,status=status.HTTP_400_BAD_REQUEST)
                
                    
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class FabricDetail(APIView):
    """
    Retrieve, update or delete a Fabric instance.
    """
    def dispatch(self,request, *args, **kwargs):
        me = RequestValidator(request.META)
        if me.user_is_exist():
            return super(FabricDetail, self).dispatch(request,*args, **kwargs)
        else:
            resp = me.invalid_token()
            return JsonResponse(resp,status=status.HTTP_400_BAD_REQUEST)

    def get_object(self, id):
        try:
            return Fabric.objects.get(pk=id)
        except Fabric.DoesNotExist:
            raise Http404

    def get(self, request, id, format=None):
        topo_detail = {}
        fabric = self.get_object(id)
        serializer = FabricGetDetailSerializer(fabric)
        data = dict(serializer.data)
        data['config_json'] = json.loads(data['config_json'])
        data['system_id'] = json.loads(data['system_id'])
        try:
            topology = Topology.objects.get(id=fabric.topology.id)
        except Topology.DoesNotExist:
            raise Http404
        
        topology_json = json.loads(topology.topology_json)
        topo_detail.update({'topology_name':topology.name})
        topo_detail.update({'topology_id':topology.id})
        topo_detail.update({'topology_json':topology_json})
        #topology_json['topology_name'] = topology.name
        #topology_json['topology_id']  = topology.id
        data['topology'] = topo_detail

        return Response(data)

    def put(self, request, id, format=None):
        success = True
        resp = {}
        resp['Error'] = ' '
        fabric_obj = self.get_object(id)
        topology_id = fabric_obj.topology.id
        serializer = FabricPutSerializer(data=request.data)
        if serializer.is_valid():
            if ((request.data['topology_id'] != topology_id) or (fabric_obj.name != request.data['name'])):
                logger.error("Failed to Update Fabric id " + str(id)\
                +" cannot change base Topology or Fabric Name")
            else:
                topology = Topology.objects.get(id=request.data['topology_id'])
                topology_json = json.loads(topology.topology_json)
                me = RequestValidator(request.META)
                fabric_obj.user_id = me.user_is_exist().user_id
                fabric_obj.validate = request.data['validate']
                fabric_obj.locked = request.data['locked']
                try:
                    sysId_list = []
                    fabric_obj.system_id = json.dumps(request.data['system_id'])
                    for swtch in request.data['system_id']:
                        sysId_list.append(swtch['system_id'])
                    dup_items = [k for k,v in Counter(sysId_list).items() if v>1]
                    if len(dup_items)>0:
                        error_string = ','.join(str(item) for item in dup_items)
                        resp['Error'] = 'System id: '+error_string+' repeated.'
                        logger.error(resp['Error'])
                        return Response(resp, status=status.HTTP_400_BAD_REQUEST)
                except:
                    fabric_obj.system_id = []
                    
                config_in_fabric = json.loads(fabric_obj.config_json)
                for config in config_in_fabric:
                    config_obj = Configuration.objects.get(id = config['configuration_id'])
                    config_obj.used -= 1
                    config_obj.save()
                fabric_obj.config_json = json.dumps(request.data['config_json'])
                for config in request.data['config_json']:
                    config_obj = Configuration.objects.get(id = config['configuration_id'])
                    config_obj.used += 1
                    config_obj.save()
                fabric_obj.submit = request.data['submit']
                fabric_obj.instance = request.data['instance']
                # filling discovery rule db
                try:
                    dis_bulkObject_list = []
                    config_obj = request.data['config_json']
                    regex  =  fabric_obj.name + "(_)([1-9][0-9]*)(_)([a-zA-Z]*-[1-9])"
                    for switch_systemId_info in request.data['system_id']:
                        if not success:
                            break
                        switch_name = (re.search(regex, switch_systemId_info['name'])).group(4)
                        replica_num = int((re.search(regex, switch_systemId_info['name'])).group(2))
                        for config in config_obj:
                            if switch_name == config['name']:
                                discoveryrule_name = 'serial_'+switch_systemId_info['system_id']
                                old_dis_rule_name = DiscoveryRule.objects.filter(fabric_id =fabric_obj.id).\
                                                    filter(switch_name=switch_systemId_info['name'])
                                if old_dis_rule_name:
                                    try:
                                        find_obj = DiscoveryRule.objects.filter(name =discoveryrule_name)
                                        if find_obj:
                                            obj = DiscoveryRule.objects.get(name = discoveryrule_name)
                                            if obj.switch_name != switch_systemId_info['name']:
                                                success = False
                                                if obj.fabric_id == fabric_obj.id:
                                                    resp['Error'] = 'Serial id: '+switch_systemId_info['system_id']\
                                                                    +' is repeated in this fabric'
                                                resp['Error'] = 'switch: '+obj.switch_name+' is assigned with: '\
                                                                +switch_systemId_info['system_id']
                                                logger.error(resp['Error'])
                                                break
                                    except:
                                        pass
                                    try:
                                        dis_obj = DiscoveryRule.objects.get(switch_name=switch_systemId_info['name'])
                                        if dis_obj.config_id != config['configuration_id']:
                                            dis_obj.config_id = config['configuration_id']
                                            dis_bulkObject_list.append(dis_obj)
#                                             dis_obj.save()
                                        if dis_obj.name != discoveryrule_name:
                                            dis_obj.name = discoveryrule_name
                                            dis_obj.subrules = [switch_systemId_info['system_id']]
                                            dis_bulkObject_list.append(dis_obj)
#                                             dis_obj.save()
                                    except:
                                        pass
                                else:    
                                    dis_rule_obj = DiscoveryRule()
                                    dis_rule_obj.priority = 100
                                    dis_rule_obj.name = discoveryrule_name
                                    dis_rule_obj.config_id = config['configuration_id']
                                    dis_rule_obj.match = 'serial_id'
                                    dis_rule_obj.subrules = [switch_systemId_info['system_id']]
                                    dis_rule_obj.fabric_id = fabric_obj.id
                                    dis_rule_obj.replica_num = replica_num
                                    dis_rule_obj.switch_name = switch_systemId_info['name']
                                    dis_bulkObject_list.append(dis_obj)
                                    # saving objects as bulk at the end
#                                     dis_rule_obj.save()
                                
                except:
                    success = False
                    logger.error('Failed to fill discoveryRule DB with fabric_id: '+str(fabric_obj.id))
                    
                
                if success:
                    if delete_fabric_rules(id):
                        if (generate_fabric_rules(request.data['name'],\
                            request.data['instance'], fabric_obj, request.data['config_json'],\
                            topology_json)):
                            logger.info("Successfully  update Fabric id: " + str(id))
                            serializer = FabricGetDetailSerializer(fabric_obj)
                            data = serializer.data
                            data['config_json'] = json.loads(data['config_json'])
                            try:
                                data['system_id'] = json.loads(data['system_id'])
                            except:
                                data['system_id'] = []
                            for obj in dis_bulkObject_list:
                                obj.save()
                            fabric_obj.save()
                            return Response(data)
                        else:
                            success = False
                            resp['Error'] = 'Failed to update Fabric'
                            logger.error("Failed to update Fabric id: " + str(id))
                    else:
                        success = False
                        resp['Error'] = 'Failed to update Fabric Rule DB'
                        logger.error("Failed to delete Rules from fabric Rule DB for Fabric id: " + str(id))
                if not success:
                    return Response(resp, status=status.HTTP_400_BAD_REQUEST)
                
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id, format=None):
        fabric = self.get_object(id)
        topology = Topology.objects.get(id=fabric.topology.id)
        config_in_fabric = json.loads(fabric.config_json)
        for config in config_in_fabric:
                    config_obj = Configuration.objects.get(id = config['configuration_id'])
                    config_obj.used -= 1
                    config_obj.save()
        try:
            topology.used -= 1
            topology.save()
        except:
            logger.error("Failed to update topology used information" + str(topology.id))
        # deleting discovery rules formed form fabric
        try:
            DiscoveryRule.objects.filter(fabric_id = id).delete()
        except:
            logger.error('failed to delete discoveryRules with fabric_id: '+str(id))
        if delete_fabric_rules(id):
            fabric.delete()
        else:
            logger.error("Failed to delete Rules from fabric Rule DB for Fabric id: " + str(id))
        return Response(status=status.HTTP_204_NO_CONTENT)


class FabricRuleDBDetail(APIView):
    def dispatch(self,request, *args, **kwargs):
        me = RequestValidator(request.META)
        if me.user_is_exist():
            return super(FabricRuleDBDetail, self).dispatch(request,*args, **kwargs)
        else:
            resp = me.invalid_token()
            return JsonResponse(resp,status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, format=None):
        try:
            fabricrule_list = FabricRuleDB.objects.filter(status = True).order_by('id')
        except  FabricRuleDB.DoesNotExist:
            raise Http404
        serializer = FabricRuleDBGetSerializer(fabricrule_list, many=True)
        index = 0
        for item in serializer.data:
            item['fabric_id'] = fabricrule_list[index].fabric.id
            index = index + 1
        return Response(serializer.data)

    def post(self, request, format=None):
        return Response(status=status.HTTP_400_BAD_REQUEST)
    def delete(self, request, id, format=None):
        return Response(status=status.HTTP_400_BAD_REQUEST)
    def put(self, request, id, format=None):
        return Response(status=status.HTTP_400_BAD_REQUEST)


class DeployedFabric(APIView):
    """
    GET deployed fabrics
    """
    def dispatch(self,request, *args, **kwargs):
        me = RequestValidator(request.META)
        if me.user_is_exist():
            return super(DeployedFabric, self).dispatch(request,*args, **kwargs)
        else:
            resp = me.invalid_token()
            return JsonResponse(resp,status=status.HTTP_400_BAD_REQUEST)
        
    def get(self, request, format=None):
        fabric_list = DeployedFabricStats.objects.order_by('fabric_id').distinct('fabric_id')
        data = []
        for fab in fabric_list:
            try:
                fabric = Fabric.objects.get(id = fab.fabric_id)
            except:
                logger.error("Fabric not found with id: " + str(fab.fabric_id))
                pass
            fabric_dict = {}
            fabric_dict['fabric_id'] = fab.fabric_id
            if fabric_dict['fabric_id'] != INVALID:
                fabric_dict['fabric_name'] = fabric.name
                replica = DeployedFabricStats.objects.order_by('replica_num').\
                          values_list('replica_num').filter(fabric_id = fab.fabric_id).distinct('replica_num')
                fabric_dict['total_replicas'] = [tuple[0]for tuple in replica]
                data.append(fabric_dict)
            else:
                pass
        serializer = DeployedFabricGetSerializer(data = data, many=True)
        if serializer.is_valid():
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class DeployedFabricDetail(APIView):
    """
    GET detailed deployed stats
    """
    def dispatch(self,request, *args, **kwargs):
        me = RequestValidator(request.META)
        if me.user_is_exist():
            return super(DeployedFabricDetail, self).dispatch(request,*args, **kwargs)
        else:
            resp = me.invalid_token()
            return JsonResponse(resp,status=status.HTTP_400_BAD_REQUEST)
        
    def get(self, request, fabric_id, replica_num, format=None):
        try:
            fabric = Fabric.objects.get(id = fabric_id)
        except:
            logger.error("fabric not found in db with id: " + str(fabric_id))
            raise Http404
        
        try:
            deployed_list = DeployedFabricStats.objects.filter(fabric_id = fabric_id).\
                                                        filter(replica_num = replica_num)
        except:
            logger.error("fabric_id: " +str(fabric_id) + " or replica_num: "+str(replica_num)\
                          + " is not in db:")
            raise Http404
        
        serializer = DeployedFabricDetailGetSerializer(deployed_list, many = True)
        resp = serializer.data
        
        for stat in resp:
            config = Configuration.objects.get(id = stat['config_id'])
            stat['config_name'] = config.name
            stat['discoveryrule_name'] = ' '
            if stat['discoveryrule_id'] != INVALID:
                try:
                    dis_obj = DiscoveryRule.objects.get(id =stat['discoveryrule_id'])
                except:
                    logger.error('Discovery rule not found with id:'+str(stat['discoveryrule_id']))
                if dis_obj.fabric_id != INVALID: 
                    stat['discoveryrule_id'] = INVALID   
                stat['discoveryrule_name'] = dis_obj.name

        data = {}
        data['fabric.id'] = fabric_id
        data['fabric_name'] = fabric.name
        data['stats'] = resp
            
        return Response(data)


class DeployedConfig(APIView):
    """
    GET fabric_stats
    """
    def dispatch(self,request, *args, **kwargs):
        me = RequestValidator(request.META)
        if me.user_is_exist():
            return super(DeployedConfig, self).dispatch(request,*args, **kwargs)
        else:
            resp = me.invalid_token()
            return JsonResponse(resp,status=status.HTTP_400_BAD_REQUEST)
    
    def get(self, request, id, format=None):
        try:
            obj = DeployedFabricStats.objects.get(id = id)
        except:
            logger.error("stats not found with id: " + str(id))
            raise Http404
        
        config_full_path = os.getcwd()+"/repo/"+obj.configuration_generated

        try:
            wrapper = FileWrapper(file(config_full_path))
        except:
            logger.error("File does not exist with: " + config_full_path)
            raise Http404
        
        response = HttpResponse(wrapper, content_type='text/plain')
        response['Content-Length'] = os.path.getsize(config_full_path)
        return response


class DeployedLogs(APIView):
    """
    GET fabric_stats
    """
    def dispatch(self,request, *args, **kwargs):
        me = RequestValidator(request.META)
        if me.user_is_exist():
            return super(DeployedLogs, self).dispatch(request,*args, **kwargs)
        else:
            resp = me.invalid_token()
            return JsonResponse(resp,status=status.HTTP_400_BAD_REQUEST)
    
    def get(self, request, id, format=None):
        try:
            logs_name = DeployedFabricStats.objects.get(id = id)
        except:
            logger.error("Stats not found with this id: " +str(id))
            resp ={}
            resp["error"] = "Logs not found"
            return JsonResponse(resp, status=status.HTTP_400_BAD_REQUEST)
        sys_fh = open(SYSLOG_FILE, "r")
        log_file = []
        for line in sys_fh:
            words = line.split()
            if logs_name.system_id == words[LOG_SEARCH_COL] or logs_name.switch_name == words[LOG_SEARCH_COL]:
                log_file.append(string.rstrip(line))
                
        return Response(log_file)
