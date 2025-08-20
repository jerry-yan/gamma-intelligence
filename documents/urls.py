# documents/urls.py
from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('upload/', views.upload_document, name='upload'),
    path('upload-user/', views.upload_user_document, name='upload_user'),
    path('list/', views.document_list, name='list'),
]