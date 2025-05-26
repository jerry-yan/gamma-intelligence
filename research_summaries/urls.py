# gamma_intelligence/urls.py
from django.contrib import admin
from django.urls import path, include
from accounts.views import HomeView, ResearchSummariesView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', HomeView.as_view(), name='home'),
    path('accounts/', include('accounts.urls')),
    path('research-summaries/', ResearchSummariesView.as_view(), name='research_summaries'),
]