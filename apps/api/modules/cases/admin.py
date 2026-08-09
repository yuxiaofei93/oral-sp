from django.contrib import admin

from .models import (
    Case,
    CaseFact,
    CaseVersion,
    DiagnosisRule,
    PatientProfile,
    PatientPromptTemplate,
    PhysicalExam,
    PhysicalExamAsset,
    ScoringItem,
    StoredAsset,
    TestDefinition,
)

admin.site.register(Case)
admin.site.register(CaseVersion)
admin.site.register(PatientProfile)
admin.site.register(CaseFact)
admin.site.register(TestDefinition)
admin.site.register(DiagnosisRule)
admin.site.register(ScoringItem)
admin.site.register(PatientPromptTemplate)
admin.site.register(PhysicalExam)
admin.site.register(PhysicalExamAsset)
admin.site.register(StoredAsset)
