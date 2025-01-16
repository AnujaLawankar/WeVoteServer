# import_export_google_play_store/urls.py
# Brought to you by We Vote. Be good.
# -*- coding: UTF-8 -*-

from django.urls import re_path

from . import views_admin

urlpatterns = [
    re_path(r'^$', views_admin.import_export_google_play_store_index_view,
            name='import_export_google_play_store_index'),
    re_path(r'^event_list/$', views_admin.google_play_store_event_list_view, name='google_play_store_event_list'),
]
