import json,unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from .selector import PanelServer


class SelectorServerTests(unittest.TestCase):
    def setUp(self):
        self.commands=[];self.server=PanelServer(lambda ticket,value:self.commands.append((ticket,value)))
        self.addCleanup(self.server.stop)
    def request(self,path,data=None,authorized=True,origin=None):
        headers={'X-LSF-Key':self.server.token}if authorized else{}
        if origin:headers['Origin']=origin
        payload=json.dumps(data).encode()if data is not None else None
        return urlopen(Request(self.server.origin+path,data=payload,headers=headers),timeout=3)
    def test_html_is_self_contained_and_state_requires_local_nonce(self):
        with self.request('/')as r:
            content=r.read();self.assertIn(b'id="drag-box"',content);self.assertIn(b'id="search"',content)
            self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])
        with self.assertRaises(HTTPError)as error:self.request('/api/state',authorized=False)
        self.assertEqual(error.exception.code,403)
    def test_foreign_origin_is_rejected_even_with_nonce(self):
        with self.assertRaises(HTTPError)as error:self.request('/api/state',origin='https://example.org')
        self.assertEqual(error.exception.code,403);self.assertFalse(self.commands)
    def test_commands_are_queued_with_tickets_and_snapshot_updates(self):
        with self.request('/api/command',dict(kind='all_enemies'))as r:answer=json.load(r)
        self.assertEqual(answer,{'ticket':1});self.assertEqual(self.commands,[(1,{'kind':'all_enemies'})])
        self.server.update(dict(cars=[],rules={},revision=3,appliedTicket=1))
        with self.request('/api/state')as r:self.assertEqual(json.load(r)['revision'],3)
    def test_non_object_command_does_not_reach_controller(self):
        with self.assertRaises(HTTPError)as error:self.request('/api/command',data=['bad'])
        self.assertEqual(error.exception.code,400);self.assertFalse(self.commands)
