import datetime
import os
import time
import uuid
from json import JSONDecodeError
from urllib.parse import urlparse

import tornado.websocket
from tornado.ioloop import PeriodicCallback
from tornado.websocket import websocket_connect
from tornado import gen
import json

from apps.devices.curtain import CurtainDevice
from apps.devices.groupDevice import GroupDevice
from setting.setting import MY_SQL_SERVER_HOST, LOCAL_SERVER_HOST, ENVIRONMENT, BASE_DIR, WEBSOCKET_SERVICE
from utils.MysqlClient import mysqlClient
from utils.logClient import logClient
from utils.my_json import json_dumps
from concurrent.futures import ThreadPoolExecutor
from tornado.concurrent import run_on_executor

class WebsocketClient():
    def __init__(self,ioloop=None,aioloop=None):
        self.ioloop = ioloop
        self.aioloop = aioloop
        self.connect_status = None
        if self.ioloop == None:
            raise TypeError('ioloop error')
        if self.aioloop == None:
            raise TypeError('aioloop error')

        PeriodicCallback(self.wsClientKeep_alive, 10000).start()
        self.meeting_room_dict = {}
        self.meeting_room_port_set = set()
        self.connectionObject = None
        self.sendDataBuffer = []
        self.waitSendDataTask = None
        self.device_init_flag = False
        self.ioloop.add_timeout(self.ioloop.time(), self.initDevie)
        self.ioloop.add_timeout(self.ioloop.time(), self.wsClientConnect)

    @gen.coroutine
    def wsClientConnect(self):
        yield logClient.tornadoInfoLog("trying to connect")
        try:
            self.connectionObject = yield websocket_connect(WEBSOCKET_SERVICE)
        except Exception as e:
            self.connectionObject = None
            self.ioloop.add_timeout(self.ioloop.time() + 1, self.wsClientConnect)
            yield logClient.tornadoInfoLog("connection error")
        else:
            yield logClient.tornadoInfoLog("connected")
            self.ioloop.add_timeout(self.ioloop.time(), self.wsClientLoopRun)
            if self.device_init_flag == True:
                yield self.meetingRoomLogin()

    @gen.coroutine
    def wsClientLoopRun(self):
        '''接收websocket服务器的信息'''
        try:
            msg = yield self.connectionObject.read_message()
        except:
            msg = None
            # return
        if msg is None:
            yield logClient.tornadoInfoLog("connection closed")
            self.connectionObject = None
            self.ioloop.add_timeout(self.ioloop.time()+1, self.wsClientConnect)
        else:
            self.ioloop.add_timeout(self.ioloop.time(), self.wsClientLoopRun)
            try:
                msg = json.loads(msg)
            except:
                return
            yield logClient.tornadoDebugLog('2---收到服务端信息：({})'.format(msg))
            type = msg.get('type')
            if type == 'control':
                topic = msg.get('topic')
                topic_list = msg.get('topic_list')
                control_event = msg.get('control_event')
                meeting_room_guid = topic_list[1]
                try:
                    port = topic_list[6]
                    port = int(port)
                except:
                    return
                meeting_room_object = self.meeting_room_dict.get(meeting_room_guid)
                if meeting_room_object == None:
                    return
                for device_guid, device_object in meeting_room_object.items():
                    if port == device_object.port or port == str(device_object.port):
                        yield device_object.controlSelf(msg)
            elif type == 'update_device' or type == 'sync_device':
                meeting_room_guid = msg.get('meeting_room_guid')
                yield self.reportSelfDevice(type_info = type,meeting_room_guid=meeting_room_guid)


    @gen.coroutine
    def wsClientKeep_alive(self):
        msg = {
            'type': 'heartbeat',
            'time':time.time(),
        }
        self.sendToService(json_dumps(msg))

    # todo:发送信息给websocket服务端
    @gen.coroutine
    def sendToService(self, msg):
        if self.connectionObject:
            try:
                self.connectionObject.write_message(msg)
            except Exception as e:
                self.sendDataBuffer.append(msg)
                self.connectionObject = None
                yield logClient.tornadoErrorLog(str(e))
        else:
            self.sendDataBuffer.append(msg)
            if self.waitSendDataTask == None:
                self.ioloop.add_timeout(self.ioloop.time(),self.sendDataBufferData)

    @gen.coroutine
    def sendDataBufferData(self):
        if self.connectionObject:
            while True:
                try:
                    msg = self.sendDataBuffer.pop(0)
                except:
                    self.waitSendDataTask = None
                    break
                try:
                    self.connectionObject.write_message(msg)
                except Exception as e:
                    self.sendDataBuffer.append(msg)
                    self.connectionObject = None
                    yield logClient.tornadoErrorLog(str(e))
                    self.waitSendDataTask = None
        else:
            self.ioloop.add_timeout(self.ioloop.time()+1, self.sendDataBufferData)

    @gen.coroutine
    def meetingRoomLogin(self):
        data = {
            'type': 'login',
            'meeting_room_list': [x for x, y in self.meeting_room_dict.items()]
        }
        yield self.sendToService(json_dumps(data))

    @gen.coroutine
    def reportSelfDevice(self,type_info,meeting_room_guid):
        device_info = yield self.getSelfDevice(meeting_room_guid)
        data = {
            'type': type_info,
            'meeting_room_device_list': device_info,
            'meeting_room_guid':meeting_room_guid,
        }
        yield self.sendToService(json_dumps(data))

    @gen.coroutine
    def getSelfDevice(self,meeting_room_guid):
        self_device_list = []
        for meeting_room_guid_, meeting_room_object in self.meeting_room_dict.items():
            if meeting_room_guid and meeting_room_guid_ != meeting_room_guid:
                    continue
            meeting_room_device_info = {
                'meeting_room_guid': meeting_room_guid_,
                'device_list': []
            }
            for device_guid, device_object in meeting_room_object.items():
                device_info = {}
                device_info['device_guid'] = device_guid
                device_info['device_name'] = device_object.name
                device_info['function_list'] = []
                device_info['gateway_id'] = ''
                device_info['port'] = device_object.port
                device_info['room_id'] = meeting_room_guid_
                for channel_guid, channel_object in device_object.channel_dict.items():
                    channel_info = {}
                    channel_info['channel_guid'] = channel_object.guid
                    channel_info['name'] = channel_object.name
                    channel_info['string_name'] = channel_object.string_name
                    channel_info['port'] = channel_object.port
                    channel_info['channel'] = channel_object.channel
                    channel_info['type'] = channel_object.type
                    channel_info['feedback'] = channel_object.feedback
                    channel_info['max_value'] = channel_object.max_value
                    channel_info['min_value'] = channel_object.min_value
                    channel_info['raw_value'] = channel_object.raw_value
                    if channel_info['feedback'] == 'channel':
                        channel_info['channel_value'] = channel_object.getSelfStatus()
                    elif channel_info['feedback'] == 'level':
                        channel_info['level_value'] = channel_object.getSelfStatus()
                    elif channel_info['feedback'] == 'string':
                        channel_info['string_value'] = channel_object.getSelfStatus()
                    elif channel_info['feedback'] == 'matrix':
                        channel_info['matrix_value'] = {'channel_guid': channel_object.getSelfStatus()}

                    device_info['function_list'].append(channel_info)
                meeting_room_device_info['device_list'].append(device_info)
            self_device_list.append(meeting_room_device_info)
        return self_device_list

    @gen.coroutine
    def initDevie(self):
        self.device_init_flag = False
        path = BASE_DIR + '/protocol_files'
        try:
            file_list = os.listdir(path)
        except FileNotFoundError as e:
            yield logClient.tornadoErrorLog(str(e))
            return
        for file_name in file_list:
            with open(os.path.join(path, file_name), 'r') as file:
                # with open(path + '/' + file_name, 'r') as file:
                msg = file.read()
                if not msg:
                    yield logClient.tornadoErrorLog('{} file is empty'.format(file_name))
                    continue
                else:
                    try:
                        protocol_info = json.loads(msg)
                    except JSONDecodeError as e:
                        yield logClient.tornadoErrorLog(str(e))
                        continue
            setup = protocol_info.get('setup')
            options = protocol_info.get('options')
            systemOnline = protocol_info.get('systemOnline')
            devices_list = protocol_info.get('devices_list')
            if not isinstance(devices_list, list):
                continue
            if isinstance(setup, dict):
                yield logClient.tornadoInfoLog('*****************setup info*****************')
                for key, value in setup.items():
                    yield logClient.tornadoInfoLog(str(key) + ':' + str(value))

            if isinstance(options, dict):
                yield logClient.tornadoInfoLog('*****************options info*****************')
                for key, value in options.items():
                    yield logClient.tornadoInfoLog(str(key) + ':' + str(value))

            if isinstance(systemOnline, dict):
                yield logClient.tornadoInfoLog('*****************systemOnline info*****************')
                for key, value in systemOnline.items():
                    yield logClient.tornadoInfoLog(str(key) + ':' + str(value))

            for device_info in devices_list:
                device_guid = device_info.get('device_guid')
                # device_name = device_info.get('device_name')
                port = device_info.get('port')
                room_id = device_info.get('room_id')
                # gateway_id = device_info.get('gateway_id')
                device_type = device_info.get('device_type')
                # function_list = device_info.get('function_list')
                self.meeting_room_port_set.add((room_id, port))
                if device_type == None:
                    device_ = GroupDevice(ioloop=self.ioloop, aioloop=self.aioloop, websocketClient=self, **device_info)
                    if room_id not in self.meeting_room_dict.keys():
                        self.meeting_room_dict[room_id] = {}
                    self.meeting_room_dict[room_id][device_guid] = device_
                else:
                    del device_info['device_type']
                    device_ = CurtainDevice(ioloop=self.ioloop, aioloop=self.aioloop, websocketClient=self,
                                            **device_info)
                    if room_id not in self.meeting_room_dict.keys():
                        self.meeting_room_dict[room_id] = {}
                    self.meeting_room_dict[room_id][device_guid] = device_
                '''
                self.meeting_room_dict结构
                {
                    'meeting_room_guid':{
                        'device_guid':device_object
                    }
                }
                '''
        yield self.meetingRoomLogin()
        self.device_init_flag = True



























