from apps.devices.baseDevice import BaseDevice
import re

from tornado import gen

from apps.devices.baseDevice import BaseDevice
from apps.devices.controlChannel import ControlChannel

class GroupDevice(BaseDevice):
    '''
    群组分类:
        1:开关类
                    type:
                    on/off
                    on
                    off
                    level
        2:全开全关类
                    type:
                    all_on/all_off
                    all_on
                    all_off
        3:状态同步类
                    type:(数字)
                        相同
        4:状态互斥类
                    type:(数字)
                        不相同
        5:全互斥类
            group_name = 0
                group_type = 0
                group_type = 1
                group_type = 2
            group_name = 1
                group_type = 0
                group_type = 1
                group_type = 2
            group_name = [0,1]
                group_type = 0  全开
                group_type = 1  全停
                group_type = 2  全关/全开全关
        5:普通通道类
    '''

    def __init__(self, ioloop, aioloop, websocketClient, device_guid, device_name, port, room_id, gateway_id, function_list):
        super(GroupDevice, self).__init__(ioloop, aioloop, websocketClient, device_guid, device_name, port,room_id, gateway_id)
        self.ioloop.add_timeout(self.ioloop.time(), self.initSelfChannel, function_list)

    @gen.coroutine
    def controlSelf(self, msg):
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
        # topic_list = msg.get('topic_list')
        control_event = msg.get('control_event')

        channel_object = self.receiveTopicToChannel.get(topic)
        if channel_object == None:
            return
        # 控制通道有效性校验
        if not channel_object.selfControlEventCheck(control_event):
            return

        #控制通道所在的群组
        control_group_name = channel_object.group_name
        #控制通道的类型
        control_group_type = channel_object.group_type
        yield channel_object.controlSelfStatus(control_event)
        status = channel_object.getSelfStatus()
        if status == None:
            return
        # print('控制通道的状态为:{}'.format(status))
        # 遍历该设备所有通道
        for channel_guid, channel_object in self.channel_dict.items():
            yield self.controlSelfGroup(channel_object,control_group_name,control_group_type,status)

        if not isinstance(control_group_name,list):
            yield self.totalChannelChange(control_group_name)

    @gen.coroutine
    def controlSelfGroup(self,channel_object,control_name,control_type,status):
        group_type = channel_object.group_type
        if type(group_type) != type(control_type):
            return
        else:
            str_type = type(group_type)

        group_name = channel_object.group_name
        if isinstance(group_name,list):
            if isinstance(control_name,list):
                #todo:两个对象所在的群组都是列表
                #eg:控制control_name =[0,1] 反馈group_name=[0,1]
                if control_name == group_name:
                    if str_type == str:
                        # 电源逻辑
                        logic_status = self.powerLogic(control_type, status, group_type, channel_object.max_value,
                                                       channel_object.min_value)
                        yield channel_object.updateSelfStatus(logic_status)
                        # print('同群组:{}更改状态为:{}'.format(channel_object.name, logic_status))
                    else:
                        # 同步互斥逻辑
                        yield channel_object.updateSelfStatus(self.syncMutualLogic(control_type,status, group_type))
            else:
                #todo:当前通道群组是列表,控制通道群组不是列表
                #eg:控制control_name =1 反馈group_name=[0,1]
                if str_type == str:
                    #电源逻辑
                    pass
                else:
                    #同步互斥逻辑
                    pass
                pass
        elif isinstance(control_name,list):
            #todo:当前通道群组不是列表,控制通道群组是列表
            #eg:控制control_name =[0,1] 反馈group_name=1
            if group_name in control_name:
                if str_type == str:
                    # 电源逻辑
                    logic_status = self.powerLogic(control_type, status, group_type, channel_object.max_value,channel_object.min_value)
                    yield channel_object.updateSelfStatus(logic_status)
                    # print('同群组:{}更改状态为:{}'.format(channel_object.name, logic_status))
                else:
                    # 同步互斥逻辑
                    yield channel_object.updateSelfStatus(self.syncMutualLogic(control_type,status, group_type))

        else:
            if control_name == group_name:
                #todo:当前通道群组不是列表,控制通道群组也不是列表
                if str_type == str:
                    #电源逻辑
                    logic_status = self.powerLogic(control_type,status,group_type,channel_object.max_value,channel_object.min_value)
                    yield channel_object.updateSelfStatus(logic_status)
                    # print('同群组:{}更改状态为:{}'.format(channel_object.name,logic_status))
                else:
                    #同步互斥逻辑
                    yield channel_object.updateSelfStatus(self.syncMutualLogic(control_type,status, group_type))

    @gen.coroutine
    def totalChannelChange(self,control_group_name):
        for channel_guid, channel_object in self.channel_dict.items():
            group_name = channel_object.group_name
            if not isinstance(group_name,list):
                continue
            else:
                group_name_list = group_name
            result_set = set()
            compare_type = channel_object.group_type
            if control_group_name in group_name_list:
                for compare_name in group_name_list:
                    result_set.add(self.getChannelObject(group_name=compare_name,group_type=compare_type).getSelfStatus())
            # print('通道:{}的状态为:{}'.format(channel_object.name,result_set))
            if len(result_set) == 1:
                yield channel_object.updateSelfStatus(list(result_set)[0])
            else:
                yield channel_object.updateSelfStatus('off')


    def getChannelObject(self,group_name,group_type):
        for channel_guid, channel_object in self.channel_dict.items():
            if group_type == channel_object.group_type and group_name == channel_object.group_name:
                return channel_object
        else:
            raise IndexError('设备:群组名为:{},群组类型为:{}的通道不存在'.format(group_name,group_type))

    def syncMutualLogic(self,control_type,control_status,group_type,):
        if control_type == group_type:
            return control_status
        else:
            if control_status == 'on':
                return 'off'
            elif control_status == 'off':
                return 'on'

    def powerLogic(self,control_type,control_status,group_type,max_value,min_value):
        if control_type == 'on':
            if group_type == 'on':
                return control_status
            elif group_type == 'on/off':
                return control_status
            elif group_type == 'off':
                return self.negativeState(control_status)
            elif group_type == 'level':
                if control_status == 'on':
                    return max_value
                elif control_status == 'off':
                    return min_value
        elif control_type == 'off':
            if group_type == 'on':
                return self.negativeState(control_status)
            elif group_type == 'on/off':
                return self.negativeState(control_status)
            elif group_type == 'off':
                return control_status
            elif group_type == 'level':
                if control_status == 'off':
                    return max_value
                elif control_status == 'on':
                    return min_value
        elif control_type == 'on/off':
            if group_type == 'on':
                return control_status
            elif group_type == 'on/off':
                return control_status
            elif group_type == 'off':
                return self.negativeState(control_status)
            elif group_type == 'level':
                if control_status == 'on':
                    return max_value
                elif control_status == 'off':
                    return min_value
        elif control_type == 'level':
            try:
                control_status = float(control_status)
                if control_status == min_value:
                    if group_type == 'on':
                        return 'off'
                    elif group_type == 'on/off':
                        return 'off'
                    elif group_type == 'off':
                        return 'on'
                    elif group_type == 'level':
                        return control_status
                else:
                    if group_type == 'on':
                        return 'on'
                    elif group_type == 'on/off':
                        return 'on'
                    elif group_type == 'off':
                        return 'off'
                    elif group_type == 'level':
                        return control_status
            except:
                pass

    def negativeState(self,status):
        if status == 'on':
            return 'off'
        elif status == 'off':
            return 'on'
        else:
            raise IndexError('status error')