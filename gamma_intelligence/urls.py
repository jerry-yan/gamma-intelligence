# gamma_intelligence/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import HomeView

admin.site.site_header = "Gamma Intelligence Admin"
admin.site.site_title = "Gamma Intelligence"
admin.site.index_title = "Welcome to Gamma Intelligence Administration"

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', HomeView.as_view(), name='home'),
    path('accounts/', include('accounts.urls')),
    path('research/', include('research_summaries.urls')),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)