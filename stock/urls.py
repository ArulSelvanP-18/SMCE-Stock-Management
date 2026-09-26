from django.urls import path
from . import views

urlpatterns = [
    # Public landing + Auth
    path("", views.landing_view, name="landing"),
    path("login/", views.login_view, name="login"),
    path("register/", views.registration_view, name="registration"),
    path("logout/", views.logout_view, name="logout"),

    # Dashboard
    path("dashboard/", views.dashboard_view, name="dashboard"),
    # Central Item Master / System Control
    path("system-control/", views.system_control_view, name="system_control"),
    path("system-control/add/", views.system_item_create_view, name="system_item_create"),
    path("system-control/<int:item_id>/update/", views.system_item_update_view, name="system_item_update"),
    path("system-control/<int:item_id>/delete/", views.system_item_delete_view, name="system_item_delete"),
    path("system-control/items/", views.system_items_api, name="system_items_api"),
    path("item-code/preview/", views.item_code_preview_api, name="item_code_preview_api"),

    # Reports & Dead Stock
    path("reports/", views.reports_view, name="reports"),
    path("reports/export/<str:fmt>/", views.reports_export_view, name="reports_export"),
    path("dead-stock/", views.dead_stock_view, name="dead_stock"),
    path("dead-stock/export/<str:fmt>/", views.dead_stock_export_view, name="dead_stock_export"),

    # Analysis: block/room/status filters + search + cumulative totals
    path("analysis/", views.analysis_view, name="analysis"),
    path("analysis/export/<str:fmt>/", views.analysis_export_view, name="analysis_export"),

    # Transfer Data
    path("transfer/", views.transfer_view, name="transfer"),
    path("transfer/floors/", views.transfer_floors_api, name="transfer_floors_api"),
    path("transfer/rooms/", views.transfer_rooms_api, name="transfer_rooms_api"),
    path("transfer/stock/", views.transfer_stock_api, name="transfer_stock_api"),
    path("transfer/execute/", views.transfer_execute_view, name="transfer_execute"),

    # Navigation: mode is "modify" or "view"
    path("<str:mode>/blocks/", views.block_list_view, name="block_list"),
    path("<str:mode>/blocks/<slug:slug>/", views.block_detail_view, name="block_detail"),
    path("<str:mode>/blocks/<slug:slug>/floor/<str:floor>/", views.floor_room_list_view, name="room_list"),
    path(
        "<str:mode>/blocks/<slug:slug>/floor/<str:floor>/room/<int:index>/",
        views.room_mini_window_view, name="room_mini_window",
    ),
    path(
        "<str:mode>/blocks/<slug:slug>/floor/<str:floor>/room/<int:index>/stock/",
        views.room_stock_view, name="room_stock",
    ),
    path(
        "<str:mode>/blocks/<slug:slug>/floor/<str:floor>/room/<int:index>/stock/insert/",
        views.stock_insert_view, name="stock_insert",
    ),
    path(
        "<str:mode>/blocks/<slug:slug>/floor/<str:floor>/room/<int:index>/stock/<int:item_id>/update/",
        views.stock_update_view, name="stock_update",
    ),
    path(
        "<str:mode>/blocks/<slug:slug>/floor/<str:floor>/room/<int:index>/stock/<int:item_id>/delete/",
        views.stock_delete_view, name="stock_delete",
    ),
    path(
        "<str:mode>/blocks/<slug:slug>/floor/<str:floor>/room/<int:index>/stock/import/",
        views.stock_import_view, name="stock_import",
    ),
    path(
        "<str:mode>/blocks/<slug:slug>/floor/<str:floor>/room/<int:index>/stock/export/<str:fmt>/",
        views.stock_export_view, name="stock_export",
    ),
    path(
        "<str:mode>/blocks/<slug:slug>/floor/<str:floor>/room/<int:index>/stock/import/template/",
        views.stock_import_template_view, name="stock_import_template",
    ),
]
