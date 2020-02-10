import json
import random

from tornado import gen

from setting.setting import COMMANDBAKC, FEEDBACK_TYPE, CONNTROL_TYPE
from utils.logClient import logClient
from utils.my_json import json_dumps

class ControlChannel():
    def __init__(self,
                 meeting_room_guid,
                 ioloop,
                 aioloop,
                 websocketClient,
                 group_name,
                 group_type,
                 channel_guid,
                 port,
                 channel,
                 name,
                 string_name,
                 type,
                 feedback,
                 raw_value,
                 min_value,
                 max_value,
                 ):
        self.meeting_room_guid = meeting_room_guid
        self.ioloop = ioloop
        self.aioloop = aioloop
        self.websocketClient = websocketClient
        self.group_name = group_name
        self.group_type = group_type
        self.guid = channel_guid
        self.channel = channel
        self.port = port
        self.string_name = string_name
        self.name = name
        if type not in CONNTROL_TYPE:
            raise TypeError('type error')
        self.type = type
        if feedback not in FEEDBACK_TYPE:
            raise TypeError('feedback error')
        self.feedback = feedback

        self.raw_value = float(raw_value)
        self.min_value = float(min_value)
        self.max_value = float(max_value)

        #更新发送和接收主题
        self.updateSelfTopic()
        #
        self.channel_value = None
        self.level_value = None
        self.string_value = None
        self.matrix_value = None
        #发送主题
        self.onceClickBign = False
        self.keepBignStatus = None
        self.initSelfStatus()
        if self.group_type == None and self.group_name == None and self.channel >= 250:
            self.ioloop.add_timeout(self.ioloop.time(),self.updateSelfStatus,'on')
        if self.type == self.feedback == 'string' and self.group_type == None and self.group_name == None:
            self.ioloop.add_timeout(self.ioloop.time(),self.auto_receive)
        #
        self.updateCallback = []

    def updateSelfTopic(self):
        '''
        info = {
                'user_id':user_id,
                'control_event':control_event,
                'now_status':now_status,
                'back_status':content.get('status')
            }
        '''
        #控制
        if self.type == 'string':  # 判断type
            self.sendTopic = '/aaiot/{}/send/controlbus/event/{}/{}/{}'.format(self.meeting_room_guid, self.type, str(self.port),self.string_name)
        else:
            self.sendTopic = '/aaiot/{}/send/controlbus/event/{}/{}/{}'.format(self.meeting_room_guid, self.type, str(self.port),str(self.channel))  # 使用channel

        #反馈
        if self.feedback != '' and self.feedback != 'none' and self.feedback != None:
            if self.feedback == 'string':  # 判断type
                self.receiveTopic = '/aaiot/{}/receive/controlbus/event/{}/{}/{}'.format(self.meeting_room_guid, self.feedback, str(self.port),self.string_name)
            else:
                self.receiveTopic = '/aaiot/{}/receive/controlbus/event/{}/{}/{}'.format(self.meeting_room_guid, self.feedback, str(self.port),str(self.channel))  # 使用channel
        else:
            self.receiveTopic = ''
        # logClient.debugLog('通道:{}的控制主题为:{},监控主题为:{}'.format(self.name,self.sendTopic,self.receiveTopic))


    def selfControlEventCheck(self,control_event):
        if self.type == 'button':
            if control_event in ['click','push','release']:
                return True
        elif self.type == 'channel':
            if control_event in ['pulsh','on','off']:
                return True
        elif self.type == 'level':
            try:
                float(control_event)
                return True
            except:
                pass
        elif self.type == 'string':
            return True
        elif self.type == 'matrix' and self.feedback == 'matrix':
            if isinstance(control_event,dict):
                if control_event.get('channel_guid') != None:
                    return True
            else:
                try:
                    if json.loads(control_event).get('channel_guid') != None:
                        return True
                except:
                    pass

    @gen.coroutine
    def websocketWrite(self,msg):
        self.websocketClient.sendToService(json_dumps(msg))

    #更新通道状态e
    @gen.coroutine
    def updateSelfStatus(self,status):
        old_status = self.getSelfStatus()
        if old_status == status:
            return
        else:
            if self.type != 'matrix':
                msg = {
                    'type':'channel_status',
                    'topic':self.receiveTopic,
                    'data':status
                }
                self.ioloop.add_timeout(self.ioloop.time(),self.websocketWrite,msg)
        if self.type == 'button' or self.type == 'channel':
            if status == 'on' or status == 'off':
                self.channel_value = status
        elif self.type == 'level':
            try:
                self.level_value = float(status)
            except:
                pass
        elif self.type == 'string':
            self.string_value = status
        elif self.type == 'macro':
            self.channel_value = status
        elif self.type == 'matrix':
            if isinstance(status,dict):
                self.matrix_value = status.get('channel_guid')
                yield logClient.tornadoDebugLog('矩阵通道:{}更新状态为:{}'.format(self.name, self.matrix_value))
            else:
                try:
                    status = json.loads(status)
                    status = status.get('channel_guid')
                    if old_status != status:
                        self.matrix_value = status
                        yield logClient.tornadoDebugLog('矩阵通道:{}更新状态为:{}'.format(self.name,self.matrix_value))
                        msg = {
                            'type': 'channel_status',
                            'topic': self.receiveTopic,
                            'data': status
                        }
                        self.ioloop.add_timeout(self.ioloop.time(),self.websocketWrite,msg)
                        # yield self.publish_function(self.receiveTopic, value, qos=2)
                except:
                    yield logClient.tornadoErrorLog(status)
        elif self.type == 'none':
            if self.feedback == 'button' or self.feedback == 'channel':
                if status == 'on' or status == 'off':
                    self.channel_value = status
            elif self.feedback == 'level':
                try:
                    self.level_value = float(status)
                except:
                    pass
            elif self.feedback == 'string':
                self.string_value = status
            elif self.feedback == 'matrix':
                if isinstance(status, dict):
                    self.matrix_value = status.get('channel_guid')
                    yield logClient.tornadoDebugLog('矩阵通道:{}更新状态为:{}'.format(self.name, self.matrix_value))
                else:
                    try:
                        status = json.loads(status)
                        self.matrix_value = status.get('channel_guid')
                        yield logClient.tornadoDebugLog('矩阵通道:{}更新状态为:{}'.format(self.name, self.matrix_value))
                    except:
                        yield logClient.tornadoErrorLog(status)
            else:
                yield logClient.tornadoErrorLog('未知通道:{}'.format(self.guid))
                return
        else:
            yield logClient.tornadoErrorLog('未知通道:{}'.format(self.guid))
            return
        for callback in self.updateCallback:
            yield callback(self.guid,self.getSelfStatus())

    @gen.coroutine
    def controlSelfStatus(self,control_event):
        if self.type == 'button':
            if control_event == 'push' or control_event == 'click':
                if self.group_type == 'on':
                    yield self.updateSelfStatus('on')
                elif self.group_type == 'off':
                    yield self.updateSelfStatus('on')
                else:
                    self_status = self.getSelfStatus()
                    if self_status == 'on':
                        yield self.updateSelfStatus('off')
                    elif self_status == 'off':
                        yield self.updateSelfStatus('on')
        elif self.type == 'channel':
            if control_event == 'on':
                yield self.updateSelfStatus('on')
            elif control_event == 'off':
                yield self.updateSelfStatus('off')
            elif control_event == 'pulsh':
                yield self.updateSelfStatus('on')
                self.ioloop.add_timeout(self.ioloop.time()+0.5,self.updateSelfStatus,'off')
        elif self.type == 'level':
            try:
                new_status = float(control_event)
                if new_status > self.max_value:
                    new_status = self.max_value
                elif new_status < self.min_value:
                    new_status = self.min_value
                yield self.updateSelfStatus(new_status)
            except:
                pass
        elif self.type == 'string':
            yield self.updateSelfStatus(str(control_event))
        elif self.type == 'matrix':
            if self.feedback == 'none':
                return
            elif self.feedback == 'matrix':
                if isinstance(control_event,dict):
                    yield self.updateSelfStatus(control_event)
                else:
                    try:
                        yield self.updateSelfStatus(json.loads(control_event))
                    except:
                        pass

    #获取当前通道状态
    def getSelfStatus(self):
        if self.type == 'button' or self.type == 'channel':
            return self.channel_value
        elif self.type == 'level':
            return float(self.level_value)
        elif self.type == 'string':
            return self.string_value
        elif self.type == 'macro':
            return self.channel_value
        elif self.feedback == 'matrix':
            return self.matrix_value
        else:
            if self.feedback == 'button' or self.feedback == 'channel':
                return self.channel_value
            elif self.feedback == 'level':
                return float(self.level_value)
            elif self.feedback == 'string':
                return self.string_value
            elif self.type == 'matrix':
                return None

    #初始化通道状态
    def initSelfStatus(self):
        if self.type == 'button' or self.type == 'channel':
            self.channel_value = 'off'
        elif self.type == 'level':
            self.level_value = self.raw_value
            if self.level_value > self.max_value or self.level_value < self.min_value:
                self.level_value = self.min_value
        elif self.type == 'string':
            self.string_value = ''
        elif self.type == 'matrix':
            self.matrix_value = None
        else:
            if self.feedback == 'button' or self.feedback == 'channel':
                self.channel_value = 'off'
            elif self.feedback == 'level':
                self.level_value = self.raw_value
                if self.level_value > self.max_value or self.level_value < self.min_value:
                    self.level_value = self.min_value
            elif self.feedback == 'string':
                self.string_value = ''
            elif self.feedback == 'matrix':
                self.matrix_value = None


    @gen.coroutine
    def getSelfControlEvent(self,goal_state):
        if goal_state == 0 or goal_state == 'off':      #目标 关
            if self.type == 'button':
                if self.getSelfStatus() == 'on':
                    return 'click'
                else:
                    return
            elif self.type == 'channel':
                if self.getSelfStatus() == 'on':
                    return 'off'
                else:
                    return
            elif self.type == 'level':
                if self.getSelfStatus() != self.min_value:
                    return self.min_value
                else:
                    return
            elif self.type == 'macro':
                if self.getSelfStatus() == 'on':
                    return 'off'
                else:
                    return
        elif goal_state == 1 or goal_state == 'on': #目标 开
            if self.type == 'button':
                if self.getSelfStatus() == 'off':
                    return 'click'
                else:
                    return
            elif self.type == 'channel':
                if self.getSelfStatus() == 'off':
                    return 'on'
                else:
                    return
            elif self.type == 'level':
                if self.getSelfStatus() != self.max_value:
                    return self.max_value
                else:
                    return
            elif self.type == 'macro':
                if self.getSelfStatus() == 'off':
                    return 'on'
                else:
                    return
        else:
            return

    @gen.coroutine
    def auto_receive(self):
        new_status = random.randint(self.min_value*10,self.max_value*10)/10
        yield self.updateSelfStatus(new_status)
        self.ioloop.add_timeout(self.ioloop.time()+random.randint(10,15), self.auto_receive)