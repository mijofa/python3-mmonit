import typing
import pathlib
import xml.etree.ElementTree

import pydantic


# FIXME: Just use 3rd-party fastapi-xml?
class XMLModel(pydantic.BaseModel):
    @classmethod
    def from_xml(cls, elem) -> typing.Self:
        return cls(**{child.tag: child.text for child in elem})


class Credentials(XMLModel):
    """
    A remote monit instance's http server credentials?

    FIXME: That doesn't seem right.
    """
    username: str
    password: str


class Server(XMLModel):
    """A remote monit instance's server config."""
    uptime: int
    poll: int
    startdelay: int
    # FIXME: Surely there's a hostname object type?
    localhostname: str
    # FIXME: What is the point in this one at all?
    controlfile: pathlib.Path

    ## Only if running a webserver?
    ## over IP
    # FIXME: Surely there's an IP address object type
    address: typing.Optional[str] = None
    # FIXME: Add some constraints like
    port: typing.Optional[typing.Annotated[int, pydantic.conint(ge=0, le=65535)]] = None
    ssl: bool = False
    ## OR over unix socket
    unixsocket: typing.Optional[pathlib.Path] = None

    ## Only if monitoring credentials?
    credentials: typing.Optional[credentials] = None

    @classmethod
    def from_xml(cls, elem) -> typing.Self:
        credentials_elems = elem.findall('./credentials')
        return cls(credentials=(Credentials.from_xml(*credentials_elems) if credentials_elems else None),
                   **{child.tag: child.text for child in elem if child.tag != 'credentials'})


# If I were designing this, I'd have this be part of the 'server' object above
class Platform(XMLModel):
    """
    A remote monit instance's server platform.
    """
    name: str  # uname -s
    release: str  # uname -r
    version: str  # uname -v
    machine: str  # uname -m

    cpu: int
    # FIXME: Does pydantic have better datatypes for M/KB/MB/GB type stuff?
    memory: int
    swap: int


class Service(XMLModel):
    """A service as configured on the remote monit instance."""
    name: str
    type: int  # FIXME: enum?
    collected_sec: int  # FIXME: timestamp?
    collected_usec: int  # FIXME: timestamp?
    status: int  # FIXME: bitmask?
    status_hint: int  # FIXME: ?
    monitor: int  # FIXME: enum?
    monitormode: int  # FIXME: enum?
    onreboot: int  # FIXME: enum?
    pendingaction: int  # FIXME: enum?

    # FIXME: This is missing a lot of attrs.
    #        ref: https://github.com/MMonit/monit/blob/release-6.0.0/src/http/xml.c#L202

    @classmethod
    def from_xml(cls, elem):
        return cls(name=elem.get('name'), **{child.tag: child.text for child in elem})  # FIXME: ...


# NOTE: This one's a little custom
class ServiceGroup(pydantic.BaseModel):
    """A group of services as configured on the remote monit instance."""
    name: str
    services: list[Service]


class Event(XMLModel):
    """An event from the remote monit instance"""

    service: str

    collected_sec: int  # FIXME: timestamp?
    collected_usec: int  # FIXME: timestamp?
    type: int  # FIXME: enum?
    id: int  # FIXME: ?
    state: int  # FIXME: enum?
    action: int  # FIXME: enum?

    message: str


class Update(pydantic.BaseModel):
    """
    An update from the remote monit instance.

    Every update includes an entire dump of the configured services, servicegroups, and server config.
    An update might include a single event if something has happened, or none at all if it's just a regular heartbeat.
    """
    # Can we store this as int or bytes and cast to/from a hex string as needed?
    id: typing.Annotated[
        str,
        # FIXME: I've only seen 32-byte lower-case hex, that doesn't mean that's all it can be.
        pydantic.StringConstraints(pattern='^[0-9a-fA-F]+$',
                                   min_length=32,
                                   max_length=32,
                                   to_lower=True)]
    # FIXME: This looks like a unix-timestamp, cast it to datetime?
    # FIXME: What even is this?
    incarnation: int
    # FIXME: Is there a 'version' object type we can/should use?
    version: tuple[int, int, int]

    server: Server
    platform: Platform
    services: list[Service]
    servicegroups: list[ServiceGroup]
    event: typing.Optional[Event]  # regular heartbeat does not include an event

    @classmethod
    def from_xml(cls, id, incarnation, version, tree) -> typing.Self:
        # FIXME: Won't crash & burn if there is duplicate tags named 'services'
        _services = [Service.from_xml(child) for child in tree.find('./services')]
        # FIXME: Won't crash & burn if there is duplicate tags named 'servicegroups'
        _servicegroups = [
            ServiceGroup(
                name=child.get('name'),
                services=[s for s in _services if s.name in [service_name.text for service_name in child]]
            ) for child in tree.find('./servicegroups')]

        event_elems = tree.findall('./event')

        return cls(id=id,
                   incarnation=incarnation,
                   version=version,
                   server=Server.from_xml(*tree.findall('./server')),
                   platform=Platform.from_xml(*tree.findall('./platform')),
                   services=_services,
                   servicegroups=_servicegroups,
                   event=(Event.from_xml(*event_elems) if event_elems else None),
        )
