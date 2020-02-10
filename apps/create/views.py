import json

from tornado import web, gen

class BaseHanderView(web.RequestHandler):
    def set_default_headers(self) -> None:
        print('调用了set_default_headers')
        self.set_header('Content-Type','application/json;charset=UTF-8')

    def write_error(self, status_code: int, **kwargs) -> None:
        print('调用write_error')
        self.write(u"<h1>{}出错了</h1>".format(status_code))
        self.write(u'<p>{}</p>'.format(kwargs.get('error_title','')))
        self.write(u'<p>{}</p>'.format(kwargs.get('error_message','')))

    def initialize(self,**kwargs) -> None:
        print('调用initialize')
        self.server = kwargs.get('server')
        self.ioloop = self.server.ioloop
        self.aioloop = self.server.aioloop


    def prepare(self) -> None:
        print('调用prepare')
        #判断请求头中参数Content-Type是不是application/json,如果是,则转换body中数据
        if self.request.headers.get('Content-Type','').startswith('application/json'):
            try:
                self.json_dict = json.loads(self.request.body)
            except:
                self.json_dict = {}
        else:
            self.json_dict = {}

    def on_finish(self) -> None:
        print('调用on_finish')
        pass

class IndexView(BaseHanderView):

    @gen.coroutine
    def get(self,*args,**kwargs):
        print(self.json_dict)
        print(self.request.arguments)
        print(self.request.body)

        print(self.get_argument('free_time'))
        print(self.get_arguments('free_time'))
        print(self.get_query_arguments('free_time'))
        print(self.get_query_argument('free_time'))
        print(self.get_body_arguments('free_time'))
        print(self.get_body_argument('free_time'),default='')

        print(self.request.body_arguments)
        self.write('hello world')