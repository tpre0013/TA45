from django.contrib import admin
from django.urls import path, include
from api.views import home_page, traffic_page  # ✅ no trailing comma

urlpatterns = [
    path('', home_page, name='home'),
    path('traffic/', traffic_page, name='traffic'),
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),  # ✅ this adds the /api/ prefix to app routes
]
