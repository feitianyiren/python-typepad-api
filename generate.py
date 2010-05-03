#!/usr/bin/env python

from cStringIO import StringIO
import json
import logging
import re
import sys

import argparse


PREAMBLE = '''
# Copyright (c) 2009-2010 Six Apart Ltd.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice,
#   this list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of Six Apart Ltd. nor the names of its contributors may
#   be used to endorse or promote products derived from this software without
#   specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""

The `typepad.api` module contains `TypePadObject` implementations of all the
content objects provided in the TypePad API.

"""

from urlparse import urljoin

from remoteobjects.dataobject import find_by_name

from typepad.tpobject import *
from typepad import fields
import typepad


'''

POSTAMBLE = """
ElsewhereAccount = Account
LinkAsset = Link

browser_upload = BrowserUploadEndpoint()
"""

HAS_OBJECT_TYPE = ('User', 'Group', 'Application', 'Asset', 'Comment', 'Favorite', 'Post', 'Photo', 'Audio', 'Video', 'Link', 'Document', )

CLASS_DOCSTRINGS = {
    'Account': """A user account on an external website.""",
    'Asset': """An item of content generated by a user.""",
    'AssetRef': """A structure that refers to an asset without including its full
    content.""",
    'AssetSource': """Information about an `Asset` instance imported from another service.""",
    'AudioLink': """A link to an audio recording.""",
    'Event': """An action that a user or group did.

    An event has an `actor`, which is the user or group that did the action; a
    set of `verbs` that describe what kind of action occured; and an `object`
    that is the object that the action was done to. In the current TypePad API
    implementation, only assets, users and groups can be the object of an
    event.

    """,
    'Favorite': """A favorite of some other asset.

    Asserts that the user_id and asset_id parameter match ^\w+$.""",
    'ImageLink': """A link to an image.

    Images hosted by TypePad can be resized with image sizing specs. See
    the `url_template` field and `at_size` method.

    """,
    'PublicationStatus': """A container for the flags that represent an asset's publication status.

    Publication status is currently represented by two flags: published and
    spam. The published flag is false when an asset is held for moderation,
    and can be set to true to publish the asset. The spam flag is true when
    TypePad's spam filter has determined that an asset is spam, or when the
    asset has been marked as spam by a moderator.

    """,
    'Relationship': """The unidirectional relationship between a pair of entities.

    A Relationship can be between a user and a user (a contact relationship),
    or a user and a group (a membership). In either case, the relationship's
    status shows *all* the unidirectional relationships between the source and
    target entities.

    """,
    'RelationshipStatus': """A representation of just the relationship types of a relationship,
    without the associated endpoints.""",
    'UserProfile': """Additional profile information about a TypePad user.

    This additional information is useful when showing information about a
    TypePad account directly, but is generally not required when linking to
    an ancillary TypePad account, such as the author of a post.

    """,
    'VideoLink': """A link to a web video.""",
    'Application': """An application that can authenticate to the TypePad API using OAuth.

    An application is identified by its OAuth consumer key, which in the case
    of a hosted group is the same as the identifier for the group itself.

    """,
    'Audio': """An entry in a blog.""",
    'Comment': """A text comment posted in reply to some other asset.""",
    'Group': """A group that users can join, and to which users can post assets.

    TypePad API social applications are represented as groups.

    """,
    'Link': """A shared link to some URL.""",
    'Photo': """An entry in a blog.""",
    'Post': """An entry in a blog.""",
    'User': """A TypePad user.

    This includes those who own TypePad blogs, those who use TypePad Connect
    and registered commenters who have either created a TypePad account or
    signed in with OpenID.

    """,
    'Video': """An entry in a blog.""",
}

CLASS_EXTRAS = {
    'ApiKey': '''
    def make_self_link(self):
        return urljoin(typepad.client.endpoint, '/api-keys/%s.json' % self.api_key)

    @classmethod
    def get_by_api_key(cls, api_key):
        """Returns an `ApiKey` instance with the given consumer key.

        Asserts that the api_key parameter matches ^\w+$."""
        assert re.match('^\w+$', api_key), "invalid api_key parameter given"
        return cls.get('/api-keys/%s.json' % api_key)
''',
    'User': '''
    @classmethod
    def get_self(cls, **kwargs):
        """Returns a `User` instance representing the account as whom the
        client library is authenticating."""
        return cls.get('/users/@self.json', **kwargs)
''',
    'UserProfile': '''
    def make_self_link(self):
        return urljoin(typepad.client.endpoint, '/users/%s/profile.json' % self.url_id)

    @classmethod
    def get_by_url_id(cls, url_id, **kwargs):
        """Returns the `UserProfile` instance with the given URL identifier."""
        prof = cls.get('/users/%s/profile.json' % url_id, **kwargs)
        prof.__dict__['url_id'] = url_id
        return prof

    @property
    def user(self):
        """Returns a `User` instance for the TypePad member whose
        `UserProfile` this is."""
        return find_by_name('User').get_by_url_id(self.url_id)
''',
}


class lazy(object):

    def __init__(self, data=None):
        if data is not None:
            self.fill(data)

    def fill(self, data):
        for key, val in data.iteritems():
            if isinstance(key, unicode):
                key = key.encode('utf-8')
            if isinstance(val, unicode):
                val = val.encode('utf-8')
            setattr(self, key, val)


class Field(lazy):

    def __init__(self, data=None):
        self.args = list()
        self.kwargs = dict()
        super(Field, self).__init__(data)

    @property
    def type(self):
        return self.__dict__['type']

    @type.setter
    def type(self, val):
        self.__dict__['type'] = val

        mo = re.match(r'(\w+)<([^>]+)>', val)
        if mo is not None:
            container, subtype = mo.groups((1, 2))

            if container in ('List', 'Stream'):
                self.field_type = 'ListOf'
                self.args.append(subtype)
                return

            if container in ('set', 'array'):
                self.field_type = 'fields.List'
            elif container == 'map':
                self.field_type = 'fields.Dict'
            else:
                raise ValueError('Unknown container type %r' % container)

            subfield = Field({'type': subtype})
            self.args.append(subfield)

            return

        if val in ('string', 'boolean', 'integer'):
            self.field_type = 'fields.Field'
        else:
            self.field_type = 'fields.Object'
            if val == 'Base':
                val = 'TypePadObject'
            self.args.append(val)

    def __str__(self):
        me = StringIO()
        if not hasattr(self, 'field_type'):
            raise ValueError("Uh this Field doesn't have a field type? (%r)" % self.__dict__)
        me.write(self.field_type)
        me.write("""(""")
        if self.args:
            me.write(', '.join(str(arg) if isinstance(arg, Field) else repr(arg) for arg in self.args))
        if self.kwargs:
            if self.args:
                me.write(', ')
            me.write(', '.join('%s=%r' % (k, v) for k, v in self.kwargs.items()))
        me.write(""")""")
        return me.getvalue()


class Property(lazy):

    def __init__(self, data):
        self.field = Field()
        super(Property, self).__init__(data)

    @property
    def name(self):
        return self.__dict__['name']

    @name.setter
    def name(self, name):
        py_name = name.replace('URL', 'Url')
        py_name = re.sub(r'[A-Z]', lambda mo: '_' + mo.group(0).lower(), py_name)
        py_name = py_name.replace('-', '_')
        if py_name != name:
            self.field.kwargs['api_name'] = name
        self.__dict__['name'] = py_name

    @property
    def type(self):
        return self.__dict__['type']

    @type.setter
    def type(self, val):
        self.__dict__['type'] = val
        self.field.type = val

    def __str__(self):
        me = StringIO()
        me.write(self.name)
        me.write(" = ")
        me.write(str(self.field))
        me.write("\n")
        if hasattr(self, 'docString'):
            me.write('"""%s"""\n' % self.docString)
        return me.getvalue()


class ObjectType(lazy):

    @property
    def properties(self):
        return self.__dict__['properties']

    @properties.setter
    def properties(self, val):
        self.__dict__['properties'] = dict((prop.name, prop) for prop in (Property(data) for data in val))

    @property
    def endpoint(self):
        return self.__dict__['endpoint']

    @endpoint.setter
    def endpoint(self, val):
        self.__dict__['endpoint'] = val
        self.endpoint_name = val['name']

        assert 'properties' in self.__dict__

        for endp in val['propertyEndpoints']:
            name = endp['name']
            # TODO: handle endpoints like Blog.comments that aren't usable without filters
            try:
                value_type = endp['resourceObjectType']
            except KeyError:
                continue
            # TODO: docstring?
            prop = Property({'name': name})
            prop.field.field_type = 'fields.Link'
            if 'resourceObjectType' not in endp:
                raise ValueError("Uh %r doesn't have a resourceObjectType? (%r)" % (name, endp))
            subfield = Field({'type': value_type['name']})
            prop.field.args.append(subfield)
            self.properties[prop.name] = prop

    def __repr__(self):
        return "<%s %s>" % (type(self).__name__, self.name)

    def __str__(self):
        me = StringIO()

        if self.name in CLASS_DOCSTRINGS:
            me.write('    """')
            me.write(CLASS_DOCSTRINGS[self.name])
            me.write('"""\n\n')

        if self.name in HAS_OBJECT_TYPE:
            me.write("""    object_type = "tag:api.typepad.com,2009:%s"\n\n""" % self.name)

        for name, prop in sorted(self.properties.items(), key=lambda x: x[0]):
            prop_text = str(prop)
            prop_text = re.sub(r'(?xms)^(?=.)', '    ', prop_text)
            me.write(prop_text)

        if hasattr(self, 'endpoint_name') and 'url_id' in self.properties:
            me.write("""
    def make_self_link(self):
        return urljoin(typepad.client.endpoint, '/%(endpoint_name)s/%%s.json' %% self.url_id)

    @classmethod
    def get_by_url_id(cls, url_id, **kwargs):
        obj = cls.get('/%(endpoint_name)s/%%s.json' %% url_id, **kwargs)
        obj.__dict__['url_id'] = url_id
        return obj
""" % {'endpoint_name': self.endpoint_name})

        if self.name in CLASS_EXTRAS:
            me.write(CLASS_EXTRAS[self.name])

        body = me.getvalue()
        if not len(body):
            body = "    pass\n"
        return """class %s(%s):\n\n%s\n\n""" % (self.name, self.parentType, body)


def generate_types(types_fn, nouns_fn, out_fn):
    with open(types_fn) as f:
        types = json.load(f)
    with open(nouns_fn) as f:
        nouns = json.load(f)

    objtypes = set()
    objtypes_by_name = dict()
    for info in types['entries']:
        if info['name'] == 'Base':
            continue
        if info['parentType'] == 'Base':
            info['parentType'] = u'TypePadObject'
        objtype = ObjectType(info)
        objtypes.add(objtype)
        objtypes_by_name[objtype.name] = objtype

    for endpoint in nouns['entries']:
        try:
            objtype = objtypes_by_name[endpoint['resourceObjectType']['name']]
        except KeyError:
            pass
        else:
            objtype.endpoint = endpoint

    wrote = set(('TypePadObject',))
    wrote_one = True
    with open(out_fn, 'w') as outfile:
        if PREAMBLE.startswith('\n'):
            outfile.write(PREAMBLE.replace('\n', '', 1))
        else:
            outfile.write(PREAMBLE)

        while objtypes and wrote_one:
            eligible_types = list()
            for objtype in list(objtypes):
                if objtype.parentType not in wrote:
                    logging.debug("Oops, can't write %s as I haven't written %s yet", objtype.name, objtype.parentType)
                    continue
                eligible_types.append(objtype)

            if not eligible_types:
                wrote_one = False
                break

            for objtype in sorted(eligible_types, key=lambda x: x.name):
                outfile.write(str(objtype))
                wrote.add(objtype.name)
                objtypes.remove(objtype)

        if not wrote_one:
            raise ValueError("Ran out of types to write (left: %s)" %
                ', '.join(('%s(%s)' % (t.name, t.parentType) for t in objtypes)))

        outfile.write(POSTAMBLE)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    class Add(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            val = getattr(namespace, self.dest, self.default)
            setattr(namespace, self.dest, val + 1)

    class Subt(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            val = getattr(namespace, self.dest, self.default)
            setattr(namespace, self.dest, val - 1)

    parser = argparse.ArgumentParser(
        description='generate a TypePad client library from json endpoints')
    parser.add_argument('--types', metavar='file', help='parse file for object type info')
    parser.add_argument('--nouns', metavar='file', help='parse file for noun endpoint info')
    parser.add_argument('-v', action=Add, nargs=0, dest='verbose', default=2, help='be more verbose')
    parser.add_argument('-q', action=Subt, nargs=0, dest='verbose', help='be less verbose')
    parser.add_argument('outfile', help='file to write library to')
    ohyeah = parser.parse_args(argv)

    log_level = ohyeah.verbose
    log_level = 0 if log_level < 0 else log_level if log_level <= 4 else 4
    log_level = list(reversed([logging.DEBUG, logging.INFO, logging.WARN, logging.ERROR, logging.CRITICAL]))[log_level]
    logging.basicConfig(level=log_level)
    logging.info('Log level set to %s', logging.getLevelName(log_level))

    generate_types(ohyeah.types, ohyeah.nouns, ohyeah.outfile)

    return 0


if __name__ == '__main__':
    sys.exit(main())
