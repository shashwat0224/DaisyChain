from django.urls import path
from . import views

urlpatterns = [
    path("search/",          views.CombinedSearchView.as_view(),  name="search"),
    path("search/direct/",   views.DirectSearchView.as_view(),    name="search-direct"),
    path("search/indirect/", views.IndirectSearchView.as_view(),  name="search-indirect"),
    path("stations/search/", views.StationSearchView.as_view(),   name="station-search"),
    path("trains/<str:train_no>/stops/", views.TrainStopsView.as_view(), name="train-stops"),
]