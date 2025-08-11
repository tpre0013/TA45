# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
    path('traffic/', TemplateView.as_view(template_name='traffic.html'), name='traffic'),
    path('trends/population/', TemplateView.as_view(template_name='population_trends.html'), name='population_trends'),
    path('trends/ownership/', TemplateView.as_view(template_name='carownership_trends.html'), name='carownership_trends'),
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
]

# Serve static files during development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])