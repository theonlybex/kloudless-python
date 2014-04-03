from .util import to_datetime, to_iso, logger
from .http import request
from . import config

import requests
import inspect

class BaseResource(dict):

    # {'key': (serializer, deserializer)}
    _serializers = {
        'created': (to_iso, to_datetime),
        'modified': (to_iso, to_datetime),
        'expiration': (to_iso, to_datetime),
        }

    _path_segment = None
    _parent_resource_class = None

    def __init__(self, id=None, parent_resource=None, configuration=None):
        if not configuration: configuration = {}
        self._configuration = config.merge(configuration)

        self['id'] = id

        # Saved state, as returned by the Kloudless API.
        self._previous_data = {}

        # Keys that used to be present that no longer are post-save.
        # Useful for more helpful error messages.
        self._removed_keys = set()

        self._parent_resource = parent_resource
        if self._parent_resource_class is not None:
            if self._parent_resource is None:
                raise Exception(
                    "A %s object or ID must be specified as this "
                    "%s object's parent." %
                    (self._parent_resource_class,
                     self.__class__.__name__))
            elif not isinstance(self._parent_resource,
                                self._parent_resource_class):
                raise Exception("The parent resource must be a %s object." %
                                self._parent_resource_class)

    def populate(self, data):
        """
        data: Response from Kloudless with data on this object.
        """
        removed = set(self.keys()) - set(data.keys())
        self._removed_keys |= removed

        id = self['id']
        self.clear()

        for k, v in data.iteritems():
            super(BaseResource, self).__setitem__(
                k, self.__class__.create_from_data(
                    v, parent_resource=self._parent_resource,
                    configuration=self._configuration))

        if 'id' not in self:
            self['id'] = id

        # Update our state.
        self._previous_data = data

    @classmethod
    def create_from_data(cls, data, parent_resource=None, configuration=None):
        resource_types = {
            'account': Account, 'file': File, 'folder': Folder, 'link': Link
            }

        if isinstance(data, list):
            return [cls.create_from_data(
                    d, parent_resource=parent_resource,
                    configuration=configuration) for d in data]
        elif isinstance(data, dict) and not isinstance(data, BaseResource):
            data = data.copy()

            for k, v in data.iteritems():
                if k in cls._serializers:
                    data[k] = cls._serializers[k][1](v)

            klass = cls
            if data.get('type') in resource_types:
                klass = resource_types[data['type']]

            instance = klass(id=data.get('id'), parent_resource=parent_resource,
                             configuration=configuration)
            instance.populate(data)
            return instance
        else:
            return data

    def serialize(self):
        """
        Converts values in the BaseResource object into primitive types.
        This helps convert the entire object to JSON.
        """
        serialized = {}
        for k, v in self.iteritems():
            if isinstance(v, BaseResource):
                serialized[k] = v.serialize()
            elif k in self._serializers:
                serialized[k] = self._serializers[k][0](v)
            else:
                serialized[k] = v
        return serialized

    @classmethod
    def list_path(cls, parent_resource):
        raise NotImplementedError("Subclasses must implement list_path.")

    def detail_path(self):
        if not self['id']:
            raise Exception("The detail_path cannot be obtained since the ID "
                            "is unknown.")
        return "%s/%s" % (self.list_path(self._parent_resource), self['id'])

    # Getter/Setter methods

    def __setattr__(self, k, v):
        if k[0] == '_' or k in self.__dict__:
            return super(BaseResource, self).__setattr__(k, v)
        else:
            self[k] = v

    def __getattr__(self, k):
        if k[0] == '_':
             raise AttributeError(k)
        try:
            return self[k]
        except KeyError, e:
            raise AttributeError(*e.args)

    def __setitem__(self, k, v):
        super(BaseResource, self).__setitem__(k, v)

    def __getitem__(self, k):
        try:
            return super(BaseResource, self).__getitem__(k)
        except KeyError, e:
            if k in self._removed_keys:
                raise KeyError(
                    "%r. The key %s was previously present but no longer is. "
                    "This is due to the object being updated with new "
                    "information returned from the Kloudless API, probably "
                    "due to the object being saved. Here are the current "
                    "attributes of this object: %s" %
                    (k, k, ', '.join(self.keys())))
            else:
                raise

    def __delitem__(self, k):
        raise TypeError(
            "Items cannot be deleted. Please set them to None instead if you "
            "wish to clear them.")

class AnnotatedList(list):
    """
    Given a deserialized response of all(), the objects returned by the API
    will be made iterable, and the other attributes will become attributes
    of this AnnotatedList object.
    """
    def __init__(self, all_data):
        objects = None
        for k, v in all_data.iteritems():
            if k == 'objects' and isinstance(v, list):
                objects = v
            else:
                setattr(self, k, v)

        if objects is None:
            raise Exception("No lists were found!")
        list.__init__(self, objects)

def allow_proxy(func):
    func.allow_proxy = True
    return func

class ListMixin(object):
    @classmethod
    @allow_proxy
    def all(cls, parent_resource=None, configuration=None, **params):
        response = request(requests.get, cls.list_path(parent_resource),
                           configuration=configuration, params=params)
        data = cls.create_from_data(
            response.json(), parent_resource=parent_resource,
            configuration=configuration)
        return AnnotatedList(data)

class RetrieveMixin(object):
    @classmethod
    @allow_proxy
    def get(cls, id, parent_resource=None, configuration=None, **params):
        instance = cls(id=id, parent_resource=parent_resource,
                       configuration=configuration)
        response = request(requests.get, instance.detail_path(),
                           configuration=configuration, params=params)
        instance.populate(response.json())
        return instance

class ReadMixin(RetrieveMixin, ListMixin):
    pass

class CreateMixin(object):
    @classmethod
    @allow_proxy
    def create(cls, parent_resource=None, configuration=None, **params):
        response = request(requests.post, cls.list_path(parent_resource),
                           configuration=configuration, data=params)
        return cls.create_from_data(
            response.json(), parent_resource=parent_resource,
            configuration=configuration)

class UpdateMixin(object):
    def save(self):
        params = self.serialize()

        new_data = {}
        for k, v in params.iteritems():
            if k not in self._previous_data or self._previous_data[k] != v:
                # Attribute is new or was updated
                new_data[k] = v

        response = request(requests.patch, cls.detail_path(),
                           configuration=instance._configuration, data=new_data)
        self.populate(response.json())

class DeleteMixin(object):
    def delete(self):
        response = request(requests.delete, cls.detail_path(),
                           configuration=instance._configuration)
        self.populate({})

class WriteMixin(CreateMixin, UpdateMixin, DeleteMixin):
    pass


class Account(BaseResource, ReadMixin, DeleteMixin):
    def __init__(self, *args, **kwargs):
        super(Account, self).__init__(*args, **kwargs)

        self._link_proxy = None
        self._file_proxy = None
        self._folder_proxy = None

    @classmethod
    def list_path(cls, parent_resource):
        return 'accounts'

    @property
    def links(self):
        """
        Create a proxy object. Whenever a function is called on it
        that is present on the underlying model, we attempt to call
        the underlying model, but throw in the parent_resource if it
        has not been specified yet.
        """
        if self._link_proxy is None:
            self._link_proxy = ResourceProxy(
                Link, parent_resource=self,
                configuration=self._configuration)
        return self._link_proxy

    @property
    def files(self):
        if self._file_proxy is None:
            self._file_proxy = ResourceProxy(
                File,
                parent_resource=self,
                configuration=self._configuration)
        return self._file_proxy

    @property
    def folders(self):
        if self._folder_proxy is None:
            self._folder_proxy = ResourceProxy(
                Folder,
                parent_resource=self,
                configuration=self._configuration)
        return self._folder_proxy

class ResourceProxy(object):
    def __init__(self, klass, parent_resource=None, configuration=None):
        self.klass = klass
        self.parent_resource = parent_resource
        self.configuration = configuration

    def __getattr__(self, name):
        method = getattr(self.klass, name, None)

        import pdb; pdb.set_trace()
        def proxy_method(self, *args, **kwargs):
            import pdb; pdb.set_trace()
            self.update_kwargs(kwargs)
            return method(*args, **kwargs)

        if inspect.ismethod(method):
            if getattr(method, 'allow_proxy', False):
                return proxy_method.__get__(self)
            else:
                return method
        else:
            raise AttributeError(name)

    def __call__(self, *args, **kwargs):
        self.update_kwargs(kwargs)
        return self.klass(*args, **kwargs)

    def update_kwargs(self, kwargs):
        if not kwargs.has_key('parent_resource'):
            kwargs['parent_resource'] = self.parent_resource
        if not kwargs.has_key('configuration'):
            kwargs['configuration'] = self.configuration

class AccountBaseResource(BaseResource):
    _parent_resource_class = Account

    def __init__(self, *accounts, **kwargs):
        """
        accounts should only be a list with 1 account in it.
        """
        if accounts:
            kwargs['parent_resource'] = accounts[0]
        super(AccountBaseResource, self).__init__(**kwargs)

    @classmethod
    def list_path(cls, account):
        account_path = account.detail_path()
        return "%s/%s" % (account_path, cls._path_segment)

class File(AccountBaseResource, RetrieveMixin, DeleteMixin, UpdateMixin):
    _path_segment = 'files'

    def contents(self):
        response = request(requests.get, "%s/contents" % self.detail_path(),
                           configuration=instance._configuration)
        return response.content

    @classmethod
    def create(cls, file_name='', parent_id='root', file_data='',
               overwrite=False, parent_resource=None, configuration=None):
        data = {
            'metadata': json.dumps({
                    'name': file_name,
                    'parent_id': parent_folder_id,
                    })
            }
        files = {'file': (file_name, file_data)}
        response = request(requests.post, cls.list_path(parent_resource),
                           data=data, files=files,
                           configuration=configuration)
        return cls.create_from_data(
            response.json(), parent_resource=parent_resource,
            configuration=configuration)

class Folder(AccountBaseResource, RetrieveMixin, DeleteMixin, UpdateMixin):
    _path_segment = 'folders'

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('id', 'root')
        super(Folder, self).__init__(*args, **kwargs)

    def contents(self):
        response = request(requests.get, "%s/contents" % self.detail_path(),
                           configuration=self._configuration)
        data = self.create_from_data(
            response.json(), parent_resource=self._parent_resource,
            configuration=self._configuration)
        return AnnotatedList(data)

class Link(AccountBaseResource, ReadMixin, WriteMixin):
    _path_segment = 'links'