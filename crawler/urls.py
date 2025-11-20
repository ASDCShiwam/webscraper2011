from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('start_scraping', views.start_scraping, name='start_scraping'),
    path('live_status', views.live_status, name='live_status'),

]
