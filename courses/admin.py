from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, Category, Course, CourseMember, CourseContent, Comment, Progress


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'is_active', 'date_joined')
    list_filter = ('role', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Role', {'fields': ('role',)}),
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)
    list_filter = ('parent',)


class CourseContentInline(admin.TabularInline):
    model = CourseContent
    extra = 1
    fields = ('order', 'name', 'video_url')
    ordering = ('order',)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'teacher', 'category', 'price', 'created_at')
    list_filter = ('teacher', 'category', 'created_at')
    search_fields = ('name', 'description')
    ordering = ('-created_at',)
    inlines = [CourseContentInline]


@admin.register(CourseMember)
class CourseMemberAdmin(admin.ModelAdmin):
    list_display = ('course_id', 'user_id', 'roles')
    list_filter = ('roles',)
    search_fields = ('user_id__username', 'course_id__name')


@admin.register(CourseContent)
class CourseContentAdmin(admin.ModelAdmin):
    list_display = ('name', 'course_id', 'order', 'parent_id')
    list_filter = ('course_id',)
    search_fields = ('name', 'description')
    ordering = ('course_id', 'order')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('content_id', 'member_id', 'comment')
    list_filter = ('content_id',)
    search_fields = ('comment',)


@admin.register(Progress)
class ProgressAdmin(admin.ModelAdmin):
    list_display = ('member', 'content', 'is_completed', 'completed_at')
    list_filter = ('is_completed',)
    search_fields = ('member__user_id__username', 'content__name')