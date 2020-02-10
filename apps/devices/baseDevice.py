
from tornado import gen

from apps.devices.controlChannel import ControlChannel
from utils.logClient import logClient

class BaseDevice():

    def __init__(self, ioloop, aioloop, websocketClient, device_guid, device_name, port, room_id, gateway_id):
        self.ioloop = ioloop
        self.aioloop = aioloop
        self.websocketClient = websocketClient
        self.guid = device_guid
        self.name = device_name
        self.port = port
        self.meeting_room_guid = room_id
        self.gateway_id = gateway_id

        self.channel_dict = {}
        self.receiveTopicToChannel = {}

    @gen.coroutine
    def initSelfChannel(self, channel_list):
        for channel_info in channel_list:
            '''
            "channel_guid": "b2eb2be4-bd7a-46d0-80d7-65e1489fe218", 
            "channel": 11, 
            "name": "回路 1 Toggle", 
            "type": "button", 
            "feedback": "channel", 
            "channel_value": "off", 
            "string_name": "", 
            "string_value": "", 
            "min_value": 0, 
            "max_value": 100, 
            "raw_value": 0, 
            "level_value": 0 
            '''
            channel_msg = {
                'group_name': channel_info.get('group_name'),
                'group_type': channel_info.get('group_type'),
                'channel_guid': channel_info.get('channel_guid'),
                'channel': channel_info.get('channel'),
                'name': channel_info.get('name'),
                'type': channel_info.get('type'),
                'feedback': channel_info.get('feedback'),
                'string_name': channel_info.get('string_name'),
                'min_value': channel_info.get('min_value'),
                'max_value': channel_info.get('max_value'),
                'raw_value': channel_info.get('raw_value'),
            }

            channel_ = ControlChannel(meeting_room_guid=self.meeting_room_guid, ioloop=self.ioloop,
                                      aioloop=self.aioloop, websocketClient=self.websocketClient, port=self.port,
                                      **channel_msg)
            receiveTopic = channel_.sendTopic
            self.channel_dict[channel_.guid] = channel_
            self.receiveTopicToChannel[receiveTopic] = channel_

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
        topic = msg.get('topic')
        topic_list = msg.get('topic_list')
        control_event = msg.get('control_event')

        channel_object = self.receiveTopicToChannel.get(topic)
        if channel_object == None:
            return
        group_name = channel_object.group_name
        if group_name == None:
            yield self.controlSelfChannel(channel_object,msg)
            return True
        else:
            return False

    @gen.coroutine
    def controlSelfChannel(self,channel_object,msg):
        '''
        :param channel_object:  通道对象
        :param msg: {
                        topic:
                        topic_list:
                        data:
                    }
        :return:
        '''
        control_event = msg.get('control_event')
        channel_type = channel_object.type
        if channel_type == 'button':
            if control_event == 'click' or control_event == 'push':
                old_status = channel_object.getSelfStatus()
                if old_status == 'on':
                    yield channel_object.updateSelfStatus('off')
                elif old_status == 'off':
                    yield channel_object.updateSelfStatus('on')
        elif channel_type == 'channel':
            if control_event == 'on' or control_event == 'off':
                yield channel_object.updateSelfStatus(control_event)
        elif channel_type == 'level':
            try:
                level_value = float(control_event)
                if level_value > channel_object.max_value:
                    yield channel_object.updateSelfStatus(channel_object.max_value)
                elif level_value < channel_object.min_value:
                    yield channel_object.updateSelfStatus(channel_object.min_value)
                else:
                    yield channel_object.updateSelfStatus(level_value)
            except:
                pass
        elif channel_type == 'string':
            if type(control_event) != str:
                string_value = str(control_event)
                yield channel_object.updateSelfStatus(string_value)
            else:
                yield channel_object.updateSelfStatus(control_event)
        else:
            yield logClient.tornadoWarningLog('未知通道类型')



