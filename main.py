import sys
import typing

import gzip

import fastapi
import xml.etree.ElementTree

import monit_xml

app = fastapi.FastAPI()


# ref: https://github.com/fastapi/fastapi/issues/4501#issuecomment-1133545028
# FIXME: Can this be a middleware?
#        The base fastapi.middleware.gzip.GZipMiddleware only works on the response, not the request
class GzipRequest(fastapi.Request):
    async def body(self) -> bytes:
        if not hasattr(self, "_body"):
            body = await super().body()
            if "gzip" in self.headers.getlist("Content-Encoding"):
                body = gzip.decompress(body)
            self._body = body
        return self._body
class GzipRoute(fastapi.routing.APIRoute):
    def get_route_handler(self) -> typing.Callable:
        original_route_handler = super().get_route_handler()
        async def custom_route_handler(request: fastapi.Request) -> fastapi.Response:
            request = GzipRequest(request.scope, request.receive)
            return await original_route_handler(request)
        return custom_route_handler
app.router.route_class = GzipRoute


@app.post("/collector")
async def collector(request: fastapi.Request):
    if request.headers['Content-Type'] != 'text/xml':
        raise Exception('Must be XML')  # FIXME: Better exception

    # # FIXME: Explicitly decode gzip request here or use a middleware/custom-route?
    # if request.headers.get('Content-Encoding') == 'gzip':
    #     incoming_data = gzip.decompress(await request.body())

    # FIXME: Use fastapi-xml? https://github.com/cercide/fastapi-xml
    incoming_data: xml.etree.ElementTree.Element = xml.etree.ElementTree.fromstring(await request.body())

    # ref: https://github.com/MMonit/monit/blob/release-6.0.0/src/http/xml.c#L98-L109
    if incoming_data.tag != 'monit':
        raise Exception('Must be "monit" XML')

    print(monit_xml.Update.from_xml(
        id=incoming_data.get('id'),
        incarnation=incoming_data.get('incarnation'),
        version=tuple(int(i) for i in incoming_data.get('version').split('.')),
        tree=incoming_data))

    # xml.etree.ElementTree.indent(incoming_data, space='\t', level=0)
    # # NOTE: 'unicode' here is a magic word to make it generate a string object instead of a bytes object
    # print(xml.etree.ElementTree.tostring(incoming_data, encoding='unicode'))

    return fastapi.responses.Response(
        # FIXME: This is not replacing the existing 'Server' header, but it works fine anyway so do we care?
        # This let's Monit know we support gzip encryption
        # FIXME: Should this be a middleware?
        headers={'Server': "mmonit/3.6 CyberIT/0.1"}
    )
