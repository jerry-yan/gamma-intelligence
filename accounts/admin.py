# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    fields = ('last_read_time', 'last_read_time_advanced')


class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined', 'get_last_read_time')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    fieldsets = UserAdmin.fieldsets + (
        ('Permissions', {'fields': ('groups',)}),
    )

    def get_last_read_time(self, obj):
        if hasattr(obj, 'profile') and obj.profile.last_read_time:
            return obj.profile.last_read_time.strftime('%Y-%m-%d %H:%M')
        return 'Never'

    def get_groups(self, obj):
        return ', '.join([g.name for g in obj.groups.all()]) or 'None'

    get_last_read_time.short_description = 'Last Read Time'
    get_last_read_time.admin_order_field = 'profile__last_read_time'


# Re-register UserAdmin
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'last_read_time', 'last_read_time_advanced', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at', 'last_read_time', 'last_read_time_advanced')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('user', 'last_read_time', 'last_read_time_advanced')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )