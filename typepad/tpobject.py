"""

The `typepad.tpobject` module houses the `TypePadObject` class and related
classes, providing a `RemoteObject` based implementation of the generic
TypePad API.

The module contains:

* the `TypePadObject` class, a `RemoteObject` subclass that enforces batch
  requesting and ``objectTypes`` behavior

* the `Link` and `LinkSet` classes, implementing the TypePad API's common link
  mechanism using objects' ``links`` attributes

* the `ListObject` class and `ListOf` metaclass, providing an interface for
  working with the TypePad API's list endpoints

"""

from urlparse import urljoin, urlparse, urlunparse
import cgi
import inspect
import sys
import urllib

from batchhttp.client import BatchError
import remoteobjects
from remoteobjects.dataobject import find_by_name
from remoteobjects.promise import PromiseError
import remoteobjects.listobject

import typepad
from typepad import fields


classes_by_object_type = {}


class TypePadObjectMetaclass(remoteobjects.RemoteObject.__metaclass__):

    def __new__(cls, name, bases, attrs):
        newcls = super(TypePadObjectMetaclass, cls).__new__(cls, name, bases, attrs)
        try:
            api_type = attrs['object_type']
        except KeyError:
            pass
        else:
            classes_by_object_type[api_type] = newcls.__name__
        return newcls


class TypePadObject(remoteobjects.RemoteObject):

    """A `RemoteObject` representing an object in the TypePad API.

    All HTTP requests made for a `TypePadObject` are made through the
    `typepad.client` instance of `batchhttp.client.BatchClient`. Unlike other
    `PromiseObject` instances, `TypePadObject` instances cannot be
    independently delivered; they must be delivered by an outside object
    (namely `typepad.client`).

    """

    __metaclass__ = TypePadObjectMetaclass

    object_type = None
    batch_requests = True

    object_types = fields.List(fields.Field(), api_name='objectTypes')

    @classmethod
    def get_response(cls, url, http=None, **kwargs):
        """Performs the given HTTP request through `typepad.client`
        `BatchClient` instance."""
        if not urlparse(url)[1]:  # network location
            url = urljoin(typepad.client.endpoint, url)
        return super(TypePadObject, cls).get_response(url, http=typepad.client, **kwargs)

    @classmethod
    def get(cls, url, *args, **kwargs):
        """Promises a new `TypePadObject` instance for the named resource.

        If parameter `url` is not an absolute URL but the `TypePadObject`
        class has been configured with a base URL, the resulting instance will
        reference the given URL relative to the base address.

        If batch requests are enabled, the request that delivers the resulting
        `TypePadObject` instance will be added to the `typepad.client`
        `BatchClient` instance's batch request. If `typepad.client` has no
        active batch request, a `PromiseError` will be raised. The `batch`
        parameter can be used to force a non-batch request if batch
        requests are enabled.

        """
        if not urlparse(url)[1]:  # network location
            url = urljoin(typepad.client.endpoint, url)

        ret = super(TypePadObject, cls).get(url, *args, **kwargs)
        ret.batch_requests = kwargs.get('batch', cls.batch_requests)
        if ret.batch_requests:
            try:
                typepad.client.batch(ret.get_request(), ret.update_from_response)
            except BatchError, ex:
                # Remember our caller in case we need to complain about
                # delivery later.
                ret._origin = inspect.stack()[1][1:4]
        return ret

    def reclass_for_data(self, data):
        """Modifies this `TypePadObject` instance to be an instance of the
        specific `TypePadObject` subclass specified in `data`.

        If the data specify a different `TypePadObject` subclass than the one
        of which `self` is an instance, `self` will be modified to be an
        instance of the described class. That is, if:

        * the `data` parameter is a dictionary containing an ``objectTypes``
          item,
        * that ``objectTypes`` item is a list of object type identifiers, and
        * the object type identifiers describe a different `TypePadObject`
          subclass besides the one `self` belongs to,

        `self` will be turned into an instance of the class specified in the
        `data` parameter's ``objectTypes`` list.

        This method returns ``True`` if the instance was changed to be a
        different class, or ``False`` if it was not modified.

        """
        # What should I be?
        objtypes = ()
        try:
            objtypes = data['objectTypes']
        except (TypeError, KeyError):
            pass

        for objtype in objtypes:
            try:
                objclsname = classes_by_object_type[objtype]
                objcls = find_by_name(objclsname)  # KeyError
            except KeyError:
                continue

            # Is that a change?
            if objcls is not self.__class__:
                self.__class__ = objcls

                # Have update_from_dict() start over.
                return True

        # We're already that class, so go ahead.
        return False

    def update_from_dict(self, data):
        """Updates this object with the given data, transforming it into an
        instance of a different `TypePadObject` subclass if necessary.

        This implementation fills this `TypePadObject` instance with the data
        in parameter `data`, as in `RemoteObject.update_from_dict()`.

        If the data specify a different `TypePadObject` subclass than the one
        of which `self` is an instance, `self` will be modified to be an
        instance of the described class. That is, if:

        * this is the first time `update_from_dict()` is called on the instance,
        * the `data` parameter is a dictionary containing an ``objectTypes``
          item,
        * that ``objectTypes`` item is a list of object type identifiers, and
        * the object type identifiers describe a different `TypePadObject`
          subclass besides the one `self` belongs to,

        `self` will be turned into an instance of the class specified in the
        `data` parameter's ``objectTypes`` list.

        Override the `reclass_for_data()` method to change when an instance is
        modified to be of a different subclass.

        """
        if self.reclass_for_data(data):
            # Redispatch from the beginning.
            return self.update_from_dict(data)

        super(TypePadObject, self).update_from_dict(data)

        if self._location is None:
            try:
                # attempt to assign the _location of this object
                # to the 'self' link relation's href
                self._location = self.links['self'].href
            except (TypeError, KeyError, AttributeError):
                pass

    def to_dict(self):
        ret = super(TypePadObject, self).to_dict()
        if 'objectTypes' not in ret and self.object_type is not None:
            ret['objectTypes'] = (self.object_type,)
        return ret

    def deliver(self):
        """Prevents self-delivery of this instance if batch requests are
        enabled for `TypePadObject` instances.

        If batch requests are not enabled, delivers the object as by
        `PromiseObject.deliver()`.

        """
        if self.batch_requests:
            if hasattr(self, '_origin'):
                origin = self._origin
                raise PromiseError("Cannot deliver %s %s created by %s at "
                    "%s line %d except by batch request"
                    % (type(self).__name__, self._location, origin[2],
                       origin[0], origin[1]))
            else:
                raise PromiseError("Cannot deliver %s %s except by batch request"
                    % (type(self).__name__, self._location))
        return super(TypePadObject, self).deliver()


class Link(TypePadObject):

    """A `TypePadObject` representing a link from to another resource.

    The target of a `Link` object may be something other than an API resource,
    such as a `User` instance's avatar image.

    """

    rel             = fields.Field()
    href            = fields.Field()
    html            = fields.Field()
    type            = fields.Field()
    width           = fields.Field()
    height          = fields.Field()
    duration        = fields.Field()
    total           = fields.Field()
    by_user         = fields.Field(api_name="byUser")
    allowed_methods = fields.List(fields.Field(), api_name='allowedMethods')

    def __repr__(self):
        """Returns a developer-readable representation of this object."""
        return "<Link %s>" % self.__dict__.get('href', hex(id(self)))


class LinkSet(set, TypePadObject):

    """A `TypePadObject` representing a set of `Link` objects.

    `LinkSet` provides convenience methods for slicing the set of `Link`
    objects by their content. For example, the `Link` with `rel="avatar"` can
    be selected with `linkset['rel__avatar']`.

    """

    def update_from_dict(self, data):
        """Fills this `LinkSet` with `Link` instances representing the given
        data."""
        self.update([Link.from_dict(x) for x in data])

    def to_dict(self):
        """Returns a list of dictionary-ized representations of the `Link`
        instances contained in this `LinkSet`."""
        return sorted([x.to_dict() for x in self])

    def __contains__(self, key):
        """Returns a boolean result for whether the `LinkSet` contains
        a `Link` matching the key, as compared to the 'rel' member of
        each `Link`.

        """

        for x in self:
            if x.rel == key:
                return True

        return False

    def __getitem__(self, key):
        """Returns the `Link` or `LinkSet` described by the given key.

        Parameter `key` should be a string containing the axis and value by
        which to slice the `LinkSet` instance, separated by two underscores.
        For example, to select the contained `Link` with a `rel` value of
        `avatar`, the key should be `rel__avatar`.

        If the axis is `rel`, a new `LinkSet` instance containing all the
        `Link` instances with the requested value for `rel` are returned.

        If the axis is `width`, the `Link` instance best matching that width
        as discovered by the `link_by_width()` method is returned.

        No other axes are supported.

        If in either case no `Link` instances match the requested criterion, a
        `KeyError` is raised.

        """
        if isinstance(key, slice):
            raise KeyError('LinkSets cannot be sliced')

        if key.startswith('rel__'):
            # Gimme all matching links.
            key = key[5:]
            return self.__class__([x for x in self if x.rel == key])
        elif key.startswith('width__'):
            width = int(key[7:])
            return self.link_by_width(width)
        elif key.startswith('size__'):
            size = int(key[7:])
            return self.link_by_size(size)
        elif key.startswith('maxwidth__'):
            width = int(key[10:])
            links_by_width = dict([(x.width, x) for x in self if x.width <= width])
            if links_by_width:
                return links_by_width.get(max(links_by_width.keys()))
            return None

        # Gimme the first matching link.
        for x in self:
            if x.rel == key:
                return x

        raise KeyError('No such link %r in this set' % key)

    def link_by_width(self, width=0):
        """Returns the `Link` instance from this `LinkSet` that best matches
        the requested display width.

        If optional parameter `width` is specified, the `Link` instance
        representing the smallest image wider or matching the `width`
        specified is returned. If there is no such image, or if `width` is
        not specified, the `Link` for the widest image is returned.

        If there are no images in this `LinkSet`, returns `None`.

        """

        if width == 0:
            # Select the widest link
            better = lambda x: best is None or best.width < x.width
        else:
            # Select the image with the specified width or just greater
            better = lambda x: width <= x.width and (best is None or x.width < best.width)

        best = None
        for x in self:
            if better(x):
                best = x

        if best is None and width != 0:
            # Try again, this time just return the widest image available
            return self.link_by_width()

        return best

    def link_by_size(self, size=0):
        """Returns the `Link` instance from this `LinkSet` that best matches
        the requested display size.

        If optional parameter `size` is specified, the `Link` instance
        representing the smallest image bigger or matching the `size`
        specified is returned. If there is no such image, or if `size` is
        not specified, the `Link` for the biggest image is returned.

        If there are no images in this `LinkSet`, returns `None`.

        """

        # highest resolution image that still fits in bounding box
        fits = None
        # smallest resolution image that is bigger than bounding box
        oversize = None
        # highest resolution image
        original = None

        for image in self:
            # logic for assigning 'oversize'
            if image.width > size or image.height > size:
                if oversize is None or (oversize.width > image.width or oversize.height > image.height):
                    oversize = image
            else:
                # logic for assigning 'fits'
                if fits is None or (fits.width < image.width or fits.height < image.height):
                    fits = image
            if original is None or (original.width < image.width or original.height < image.height):
                original = image

        if size == 0:
            return original
        else:
            return fits or oversize or original


class ListOf(remoteobjects.listobject.PageOf, TypePadObjectMetaclass):

    _modulename = 'typepad.tpobject._lists'


class ListObject(TypePadObject, remoteobjects.PageObject):

    """A `TypePadObject` representing a list of other `TypePadObject`
    instances.

    Endpoints in the TypePad API can be either objects themselves or sets of
    objects, which are represented in the client library as `ListObject`
    instances. As the API lists are homogeneous, all `ListObject` instances
    you'll use in practice are configured for particular `TypePadObject`
    classes (their "entry classes"). A `ListObject` instance will hold only
    instances of its configured class.

    The primary way to reference a `ListObject` class is to call its
    metaclass, `ListOf`, with a reference to or name of that class.

    >>> ListOfEntry = ListOf(Entry)

    For an `Entry` list you then fetch with the `ListOfEntry` class's `get()`
    method, all the entities in the list resource's `entries` member will be
    decoded into `Entry` instances.

    """

    __metaclass__ = ListOf

    total_results = fields.Field(api_name='totalResults')
    start_index   = fields.Field(api_name='startIndex')
    links         = fields.Object('LinkSet')
    entries       = fields.List(fields.Field())

    filterorder = ['following', 'follower', 'friend', 'nonreciprocal',
        'published', 'unpublished', 'spam', 'admin', 'member',
        'by-group', 'by-user', 'photo', 'post', 'video', 'audio', 'comment',
        'link']

    def count(self):
        return int(self.total_results)

    def filter(self, **kwargs):
        """Returns a new `ListObject` instance representing the same endpoint
        as this `ListObject` instance with the additional filtering applied.

        This method filters the `ListObject` as does
        `remoteobjects.ListObject.filter()`, but specially treats filters
        defined in the TypePad API. These special filters are not added in as
        query parameters but as path components.

        """
        # Split the list's URL into URL parts, filters, and queryargs.
        parts = list(urlparse(self._location))
        queryargs = cgi.parse_qs(parts[4], keep_blank_values=True)
        queryargs = dict([(k, v[0]) for k, v in queryargs.iteritems()])

        oldpath = parts[2]
        if not oldpath.endswith('.json'):
            raise AssertionError('oldpath %r does not end in %r' % (oldpath, '.json'))
        path = oldpath[:-5].split('/')

        filters = dict()
        newpath = list()
        pathparts = iter(path)
        for x in pathparts:
            if x.startswith('@'):
                x = x[1:]
                if x in ('by-group', 'by-user'):
                    filters[x] = pathparts.next()
                else:
                    filters[x] = True
            else:
                newpath.append(x)

        # Add kwargs into the filters and queryargs as appropriate.
        for k, v in kwargs.iteritems():
            # handle case where value is a TypePadObject. If it is, check for
            # 'url_id' and if present, use that. If not, raise an exception
            if isinstance(v, typepad.api.TypePadObject):
                if hasattr(v, 'url_id'):
                    v = v.url_id
                else:
                    raise ValueError("invalid object filter value for parameter %k; object must have a url_id property to filter by object" % k)
            # Convert by_group to by-group.
            k = k.replace('_', '-')
            # Convert by_group=7 to by_group='7'.
            v = str(v)

            if k in self.filterorder:
                filters[k] = v
            else:
                queryargs[k] = v

        # Put the filters back on the URL path in API order.
        keys = filters.keys()
        keys.sort(key=self.filterorder.index)
        for k in keys:
            if filters[k]:
                newpath.append('@' + k)
                if k in ('by-group', 'by-user'):
                    newpath.append(filters[k])

        # Coalesce the URL back into a string and make a new List from it.
        parts[2] = '/'.join(newpath) + '.json'
        parts[4] = urllib.urlencode(queryargs)
        newurl = urlunparse(parts)

        ret = self.get(newurl)
        return ret

    def __getitem__(self, key):
        """Returns the specified members of the `ListObject` instance's
        `entries` list or, if the `ListObject` has not yet been delivered,
        filters the `ListObject` according to the given slice."""
        if self._delivered or not isinstance(key, slice):
            return self.entries[key]
        args = dict()
        if key.start is not None:
            args['start_index'] = key.start
            if key.stop is not None:
                args['max_results'] = key.stop - key.start
        elif key.stop is not None:
            args['max_results'] = key.stop
        return self.filter(**args)
