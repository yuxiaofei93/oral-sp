from django.contrib import admin

from .models import ClassGroup, ClassMembership, Course, CourseTeacher

admin.site.register(Course)
admin.site.register(ClassGroup)
admin.site.register(CourseTeacher)
admin.site.register(ClassMembership)

