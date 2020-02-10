from tornado import gen

from apps.devices.baseDevice import BaseDevice
from apps.devices.controlChannel import ControlChannel

from utils.MysqlClient import mysqlClient
from utils.logClient import logClient
from utils.my_json import json_dumps
class CurtainDevice(BaseDevice):
    '''
    group_name 相同为一组
    group_name相同情况下:
        同组通道互斥
        group_type为0     开
        group_type为1     停
        group_type为2     关
        group_type为3     level
        group_type为4     全开
        group_type为5     全停
        group_type为6     全停
    '''
    def __init__(self,ioloop,aioloop,websocketClient,device_guid,device_name,port,room_id,gateway_id,function_list):
        super(CurtainDevice, self).__init__(ioloop, aioloop, websocketClient, device_guid, device_name, port, room_id,gateway_id)
        self.ioloop.add_timeout(self.ioloop.time(), self.initSelfChannel, function_list)

        self.autoAddChangeTask = []
        self.autoAddChangeTaskControl = []
        self.autoReduceChangeTask = []
        self.autoReduceChangeTaskControl = []
    @gen.coroutine
    def controlSelf(self,msg):
        '''
        :param msg: {
            topic:
            topic_list:
            data:
        }
        :return:
        '''
        result = yield super().controlSelf(msg)
        if result:
            return

        topic = msg.get('topic')
        topic_list = msg.get('topic_list')
        control_event = msg.get('control_event')
        channel_object = self.receiveTopicToChannel.get(topic)
        if channel_object == None:
            return
        group_name = channel_object.group_name
        group_type = channel_object.group_type
        status = channel_object.getSelfStatus()
        if control_event == 'click' or control_event == 'push':
            yield self.updateGroupStatus(group_type, group_name)
        else:
            return
    @gen.coroutine
    def autoAddLevel(self,channel_object,timeout,group_name):
        now_value = channel_object.getSelfStatus()
        try:
            now_value = int(now_value)
        except:
            return
        now_value += 1
        if now_value > channel_object.max_value:
            now_value = channel_object.max_value
            yield channel_object.updateSelfStatus(now_value)
            self.autoAddChangeTaskControl[group_name] = None
            self.autoAddChangeTask[group_name] = None
            yield logClient.tornadoWarningLog('增加到最大值退出:{}'.format(group_name))
            return
        yield channel_object.updateSelfStatus(now_value)
        if self.autoAddChangeTaskControl[group_name] == None:
            self.autoAddChangeTask[group_name] = self.ioloop.add_timeout(self.ioloop.time() + timeout, self.autoAddLevel,channel_object, timeout, group_name)
        else:
            self.autoAddChangeTaskControl[group_name] = None
            self.autoAddChangeTask[group_name] = None
            yield logClient.tornadoWarningLog('增加重复任务被删除:{}'.format(group_name))
    @gen.coroutine
    def autoReduceLevel(self, channel_object, timeout,group_name):
        now_value = channel_object.getSelfStatus()
        try:
            now_value = int(now_value)
        except:
            return
        now_value -= 1
        if now_value < channel_object.min_value:
            now_value = channel_object.min_value
            yield channel_object.updateSelfStatus(now_value)
            self.autoReduceChangeTaskControl[group_name] = None
            self.autoReduceChangeTask[group_name] = None
            yield logClient.tornadoWarningLog('减少到最小值退出:{}'.format(group_name))
            return
        yield channel_object.updateSelfStatus(now_value)
        if self.autoReduceChangeTaskControl[group_name] == None:
            self.autoReduceChangeTask[group_name] = self.ioloop.add_timeout(self.ioloop.time() + timeout, self.autoReduceLevel,channel_object, timeout, group_name)
        else:
            self.autoReduceChangeTaskControl[group_name] = None
            self.autoReduceChangeTask[group_name] = None
            yield logClient.tornadoWarningLog('减少重复任务被删除:{}'.format(group_name))

    @gen.coroutine
    def updateGroupStatus(self,group_type,group_name=None):
        for channel_guid,channel_object in self.channel_dict.items():
            group_name_ = channel_object.group_name
            group_type_ = channel_object.group_type
            if group_name == group_name_:
                if group_type in [0,1,2]:
                    if group_type == group_type_:
                        yield channel_object.updateSelfStatus('on')
                    elif group_type_ == 3:
                        if group_type == 0:
                            #level减少
                            while len(self.autoAddChangeTask) < group_name + 1:
                                self.autoAddChangeTask.append(None)
                            while len(self.autoAddChangeTaskControl) < group_name + 1:
                                self.autoAddChangeTaskControl.append(None)

                            while len(self.autoReduceChangeTask) < group_name + 1:
                                self.autoReduceChangeTask.append(None)
                            while len(self.autoReduceChangeTaskControl) < group_name + 1:
                                self.autoReduceChangeTaskControl.append(None)

                            if self.autoReduceChangeTask[group_name] == None:
                                timeout = 0.1
                                yield logClient.tornadoDebugLog('新建减少重复任务:{}'.format(group_name))
                                self.autoReduceChangeTask[group_name] = self.ioloop.add_timeout(self.ioloop.time(),self.autoReduceLevel,channel_object,timeout,group_name)

                            if self.autoAddChangeTask[group_name] != None and self.autoAddChangeTaskControl[group_name] != True:
                                self.autoAddChangeTaskControl[group_name] = True
                                yield logClient.tornadoDebugLog('同时删除增加重复任务:{}'.format(group_name))
                        elif group_type == 1:
                            #level停止
                            while len(self.autoAddChangeTask) < group_name+1:
                                self.autoAddChangeTask.append(None)
                            while len(self.autoAddChangeTaskControl) < group_name+1:
                                self.autoAddChangeTaskControl.append(None)

                            while len(self.autoReduceChangeTask) < group_name+1:
                                self.autoReduceChangeTask.append(None)
                            while len(self.autoReduceChangeTaskControl) < group_name+1:
                                self.autoReduceChangeTaskControl.append(None)


                            if self.autoAddChangeTask[group_name]:
                                self.autoAddChangeTaskControl[group_name] = True
                                yield logClient.tornadoDebugLog('删除增加重复任务:{}'.format(group_name))
                            if self.autoReduceChangeTask[group_name]:
                                self.autoReduceChangeTaskControl[group_name] = True
                                yield logClient.tornadoDebugLog('删除减少重复任务:{}'.format(group_name))

                        elif group_type == 2:
                            #level增加
                            while len(self.autoAddChangeTask) < group_name + 1:
                                self.autoAddChangeTask.append(None)
                            while len(self.autoAddChangeTaskControl) < group_name + 1:
                                self.autoAddChangeTaskControl.append(None)

                            while len(self.autoReduceChangeTask) < group_name + 1:
                                self.autoReduceChangeTask.append(None)
                            while len(self.autoReduceChangeTaskControl) < group_name + 1:
                                self.autoReduceChangeTaskControl.append(None)

                            if self.autoAddChangeTask[group_name] == None:
                                timeout = 0.1
                                yield logClient.tornadoDebugLog('新建增加重复任务:{}'.format(group_name))
                                self.autoAddChangeTask[group_name] = self.ioloop.add_timeout(self.ioloop.time(),self.autoAddLevel,channel_object, timeout,group_name)

                            if self.autoReduceChangeTask[group_name] != None and self.autoReduceChangeTaskControl[group_name] != True:
                                self.autoReduceChangeTaskControl[group_name] = True
                                yield logClient.tornadoDebugLog('同时删除减少重复任务:{}'.format(group_name))

                    else:
                        yield channel_object.updateSelfStatus('off')
                else:
                    continue
            #全开
            if group_type == 4:
                for channel_guid, channel_object in self.channel_dict.items():
                    group_type__ = channel_object.group_type
                    group_name__ = channel_object.group_name
                    if group_type__ == 0:
                        yield channel_object.updateSelfStatus('on')
                    elif group_type__ == 1:
                        yield channel_object.updateSelfStatus('off')
                    elif group_type__ == 2:
                        yield channel_object.updateSelfStatus('off')
                    elif group_type__ == 3:
                        #level减少
                        while len(self.autoAddChangeTask) < group_name__ + 1:
                            self.autoAddChangeTask.append(None)
                        while len(self.autoAddChangeTaskControl) < group_name__ + 1:
                            self.autoAddChangeTaskControl.append(None)

                        while len(self.autoReduceChangeTask) < group_name__ + 1:
                            self.autoReduceChangeTask.append(None)
                        while len(self.autoReduceChangeTaskControl) < group_name__ + 1:
                            self.autoReduceChangeTaskControl.append(None)

                        if self.autoReduceChangeTask[group_name__] == None:
                            timeout = 0.1
                            yield logClient.tornadoDebugLog('新建减少重复任务:{}'.format(group_name__))
                            self.autoReduceChangeTask[group_name__] = self.ioloop.add_timeout(self.ioloop.time(), self.autoReduceLevel, channel_object, timeout, group_name__)

                        if self.autoAddChangeTask[group_name__] != None and self.autoAddChangeTaskControl[group_name__] != True:
                            self.autoAddChangeTaskControl[group_name__] = True
                            yield logClient.tornadoDebugLog('同时删除增加重复任务:{}'.format(group_name__))
            #全停
            elif group_type == 5:
                for channel_guid, channel_object in self.channel_dict.items():
                    group_type__ = channel_object.group_type
                    group_name__ = channel_object.group_name
                    if group_type__ == 0:
                        yield channel_object.updateSelfStatus('off')
                    elif group_type__ == 1:
                        yield channel_object.updateSelfStatus('on')
                    elif group_type__ == 2:
                        yield channel_object.updateSelfStatus('off')
                    elif group_type__ == 3:
                        # level停止
                        while len(self.autoAddChangeTask) < group_name__ + 1:
                            self.autoAddChangeTask.append(None)
                        while len(self.autoAddChangeTaskControl) < group_name__ + 1:
                            self.autoAddChangeTaskControl.append(None)

                        while len(self.autoReduceChangeTask) < group_name__ + 1:
                            self.autoReduceChangeTask.append(None)
                        while len(self.autoReduceChangeTaskControl) < group_name__ + 1:
                            self.autoReduceChangeTaskControl.append(None)

                        if self.autoAddChangeTask[group_name__] and self.autoAddChangeTaskControl[group_name__] != True:
                            self.autoAddChangeTaskControl[group_name__] = True
                            yield logClient.tornadoDebugLog('删除增加重复任务:{}'.format(group_name__))
                        if self.autoReduceChangeTask[group_name__] and self.autoReduceChangeTaskControl[group_name__] != True:
                            self.autoReduceChangeTaskControl[group_name__] = True
                            yield logClient.tornadoDebugLog('删除减少重复任务:{}'.format(group_name__))
            #全关
            elif group_type == 6:
                for channel_guid, channel_object in self.channel_dict.items():
                    group_type__ = channel_object.group_type
                    group_name__ = channel_object.group_name
                    if group_type__ == 0:
                        yield channel_object.updateSelfStatus('off')
                    elif group_type__ == 1:
                        yield channel_object.updateSelfStatus('off')
                    elif group_type__ == 2:
                        yield channel_object.updateSelfStatus('on')
                    elif group_type__ == 3:
                        # level增加
                        while len(self.autoAddChangeTask) < group_name__ + 1:
                            self.autoAddChangeTask.append(None)
                        while len(self.autoAddChangeTaskControl) < group_name__ + 1:
                            self.autoAddChangeTaskControl.append(None)

                        while len(self.autoReduceChangeTask) < group_name__ + 1:
                            self.autoReduceChangeTask.append(None)
                        while len(self.autoReduceChangeTaskControl) < group_name__ + 1:
                            self.autoReduceChangeTaskControl.append(None)

                        if self.autoAddChangeTask[group_name__] == None:
                            timeout = 0.1
                            yield logClient.tornadoDebugLog('新建增加重复任务:{}'.format(group_name__))
                            self.autoAddChangeTask[group_name__] = self.ioloop.add_timeout(self.ioloop.time(),self.autoAddLevel,channel_object, timeout,group_name__)

                        if self.autoReduceChangeTask[group_name__] != None and self.autoReduceChangeTaskControl[group_name__] != True:
                            self.autoReduceChangeTaskControl[group_name__] = True
                            yield logClient.tornadoDebugLog('同时删除减少重复任务:{}'.format(group_name__))
        #全开反馈
        for channel_guid, channel_object in self.channel_dict.items():
            group_type___ = channel_object.group_type
            if group_type___ == 0:
                status = channel_object.getSelfStatus()
                if status == 'off':
                    for channel_guid, channel_object in self.channel_dict.items():
                        group_type____ = channel_object.group_type
                        if group_type____ == 4:
                            yield channel_object.updateSelfStatus('off')
                    break
        else:
            for channel_guid, channel_object in self.channel_dict.items():
                group_type____ = channel_object.group_type
                if group_type____ == 4:
                    yield channel_object.updateSelfStatus('on')
        #全停反馈
        for channel_guid, channel_object in self.channel_dict.items():
            group_type___ = channel_object.group_type
            if group_type___ == 1:
                status = channel_object.getSelfStatus()
                if status == 'off':
                    for channel_guid, channel_object in self.channel_dict.items():
                        group_type____ = channel_object.group_type
                        if group_type____ == 5:
                            yield channel_object.updateSelfStatus('off')
                    break
        else:
            for channel_guid, channel_object in self.channel_dict.items():
                group_type____ = channel_object.group_type
                if group_type____ == 5:
                    yield channel_object.updateSelfStatus('on')
        # 全关反馈
        for channel_guid, channel_object in self.channel_dict.items():
            group_type___ = channel_object.group_type
            if group_type___ == 2:
                status = channel_object.getSelfStatus()
                if status == 'off':
                    for channel_guid, channel_object in self.channel_dict.items():
                        group_type____ = channel_object.group_type
                        if group_type____ == 6:
                            yield channel_object.updateSelfStatus('off')
                    break
        else:
            for channel_guid, channel_object in self.channel_dict.items():
                group_type____ = channel_object.group_type
                if group_type____ == 6:
                    yield channel_object.updateSelfStatus('on')
