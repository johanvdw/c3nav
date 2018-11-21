from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotModified, HttpResponseRedirect
from django.shortcuts import render
from django.utils.cache import patch_vary_headers
from django.utils.translation import get_language

from c3nav.editor.models import ChangeSet
from c3nav.mapdata.models.access import AccessPermission
from c3nav.mapdata.utils.user import can_access_editor


def sidebar_view(func=None, select_related=None, api_hybrid=False):
    if func is None:
        def wrapped(inner_func):
            return sidebar_view(inner_func, select_related=select_related, api_hybrid=api_hybrid)
        return wrapped

    @wraps(func)
    def wrapped(request, *args, api=False, **kwargs):
        if api and api_hybrid:
            raise Exception('API call on a view without api_hybrid!')

        if not can_access_editor(request):
            raise PermissionDenied

        request.changeset = ChangeSet.get_for_request(request, select_related)

        if api:
            return call_api_hybrid_view_for_api(func, request, *args, **kwargs)

        ajax = request.is_ajax() or 'ajax' in request.GET
        if not ajax:
            request.META.pop('HTTP_IF_NONE_MATCH', None)

        if api_hybrid:
            response = call_api_hybrid_view_for_html(func, request, *args, **kwargs)
        else:
            response = func(request, *args, **kwargs)

        if ajax:
            if isinstance(response, HttpResponseRedirect):
                return render(request, 'editor/redirect.html', {'target': response['location']})
            if not isinstance(response, HttpResponseNotModified):
                response.write(render(request, 'editor/fragment_nav.html', {}).content)
            response['Cache-Control'] = 'no-cache'
            patch_vary_headers(response, ('X-Requested-With', ))
            return response
        if isinstance(response, HttpResponseRedirect):
            return response
        response = render(request, 'editor/map.html', {'content': response.content.decode()})
        response['Cache-Control'] = 'no-cache'
        patch_vary_headers(response, ('X-Requested-With', ))
        return response
    wrapped.api_hybrid = api_hybrid

    return wrapped


def call_api_hybrid_view_for_api(func, request, *args, **kwargs):
    response = func(request, *args, **kwargs)
    return response


def call_api_hybrid_view_for_html(func, request, *args, **kwargs):
    response = func(request, *args, **kwargs)
    return response


def etag_func(request, *args, **kwargs):
    try:
        changeset = request.changeset
    except AttributeError:
        changeset = ChangeSet.get_for_request(request)
        request.changeset = changeset

    return (get_language() + ':' + changeset.raw_cache_key_by_changes + ':' +
            AccessPermission.cache_key_for_request(request, with_update=False) + ':' + str(request.user.pk or 0)
            + ':' + str(int(request.user_permissions.can_access_base_mapdata))
            + ':' + str(int(request.user.is_superuser)))
