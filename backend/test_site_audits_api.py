import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.abspath('.'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from apps.projects.models import Project
from apps.seo.models import SiteAudit, AuditIssue, AuditStatus, IssueSeverity

User = get_user_model()

def run_site_audits_tests():
    print("==========================================")
    print("   DOXARANK SITE AUDITS API TEST SUITE   ")
    print("==========================================\n")

    client = APIClient()

    # Clean up test users
    email_a = "audit_runner_a@doxarank.com"
    email_b = "audit_runner_b@doxarank.com"
    User.objects.filter(email__in=[email_a, email_b]).delete()

    user_a = User.objects.create_user(
        email=email_a,
        password="Password123!",
        first_name="Audit",
        last_name="TesterA"
    )
    user_b = User.objects.create_user(
        email=email_b,
        password="Password123!",
        first_name="Audit",
        last_name="TesterB"
    )

    try:
        # Create projects for both users
        proj_a = Project.objects.create(
            owner=user_a,
            name="Addis Tech Portal",
            website_url="https://addistech.et"
        )
        proj_b = Project.objects.create(
            owner=user_b,
            name="Shega Insights",
            website_url="https://shega.co"
        )

        # 1. TEST UNAUTHENTICATED GET REJECTED
        print("1. Testing Unauthenticated Access Rejection (GET /api/seo/audits/ & /api/seo/issues/)...")
        res_audits_unauth = client.get('/api/seo/audits/')
        assert res_audits_unauth.status_code == status.HTTP_401_UNAUTHORIZED
        res_issues_unauth = client.get('/api/seo/issues/')
        assert res_issues_unauth.status_code == status.HTTP_401_UNAUTHORIZED
        print("   [PASS] 401 Unauthorized returned for unauthenticated requests.")

        # 2. USER A CAN CREATE AUDIT FOR USER A'S PROJECT
        print("\n2. Testing Audit Creation by User A for User A's Project...")
        client.force_authenticate(user=user_a)
        res_a_create = client.post('/api/seo/audits/', {
            'project': proj_a.id,
            'status': 'pending',
            'score': 85
        }, format='json')
        assert res_a_create.status_code == status.HTTP_201_CREATED, f"Failed: {res_a_create.data}"
        audit_a_id = res_a_create.data['id']
        assert res_a_create.data['project'] == proj_a.id
        assert res_a_create.data['project_name'] == "Addis Tech Portal"
        assert res_a_create.data['score'] == 85
        assert res_a_create.data['status'] == 'pending'
        print(f"   [PASS] User A created SiteAudit #{audit_a_id} with score 85.")

        # 3. USER B CAN CREATE AUDIT FOR USER B'S PROJECT
        print("\n3. Testing Audit Creation by User B for User B's Project...")
        client.force_authenticate(user=user_b)
        res_b_create = client.post('/api/seo/audits/', {
            'project': proj_b.id,
            'status': 'running'
        }, format='json')
        assert res_b_create.status_code == status.HTTP_201_CREATED
        audit_b_id = res_b_create.data['id']
        assert res_b_create.data['project'] == proj_b.id
        assert res_b_create.data['project_name'] == "Shega Insights"
        assert res_b_create.data['status'] == 'running'
        print(f"   [PASS] User B created SiteAudit #{audit_b_id} for Project #{proj_b.id}.")

        # 4. USER A CANNOT CREATE AUDIT FOR USER B'S PROJECT
        print("\n4. Testing Cross-User Project Audit Creation Block...")
        client.force_authenticate(user=user_a)
        res_cross_create = client.post('/api/seo/audits/', {
            'project': proj_b.id, # User B's project
            'status': 'pending'
        }, format='json')
        assert res_cross_create.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Blocked with 400 Bad Request (Ownership validation).")

        # 5. USER A ONLY SEES OWN AUDITS
        print("\n5. Testing List Isolation (User A only sees own audits)...")
        res_a_list = client.get('/api/seo/audits/')
        assert res_a_list.status_code == status.HTTP_200_OK
        audit_ids = [a['id'] for a in res_a_list.data]
        assert audit_a_id in audit_ids
        assert audit_b_id not in audit_ids
        print(f"   [PASS] User A list contains only own audits ({len(audit_ids)} items). User B's audit is isolated.")

        # 6. USER A CANNOT RETRIEVE USER B'S AUDIT
        print("\n6. Testing Cross-User Audit Retrieval Block (GET /api/seo/audits/<user_b_audit_id>/)...")
        res_cross_get = client.get(f'/api/seo/audits/{audit_b_id}/')
        assert res_cross_get.status_code == status.HTTP_404_NOT_FOUND
        print("   [PASS] Blocked with 404 Not Found.")

        # 7. USER A CANNOT MODIFY USER B'S AUDIT
        print("\n7. Testing Cross-User Audit Modification Block (PATCH /api/seo/audits/<user_b_audit_id>/)...")
        res_cross_patch = client.patch(f'/api/seo/audits/{audit_b_id}/', {'score': 99}, format='json')
        assert res_cross_patch.status_code == status.HTTP_404_NOT_FOUND
        b_audit_obj = SiteAudit.objects.get(id=audit_b_id)
        assert b_audit_obj.score != 99
        print("   [PASS] Blocked with 404 Not Found. Audit record unchanged.")

        # 8. USER A CANNOT DELETE USER B'S AUDIT
        print("\n8. Testing Cross-User Audit Deletion Block (DELETE /api/seo/audits/<user_b_audit_id>/)...")
        res_cross_delete = client.delete(f'/api/seo/audits/{audit_b_id}/')
        assert res_cross_delete.status_code == status.HTTP_404_NOT_FOUND
        assert SiteAudit.objects.filter(id=audit_b_id).exists()
        print("   [PASS] Blocked with 404 Not Found. Audit record intact.")

        # 9. USER A CAN UPDATE THEIR OWN AUDIT
        print("\n9. Testing Update Own Audit (PATCH /api/seo/audits/<user_a_audit_id>/)...")
        completed_ts = timezone.now().isoformat()
        res_a_update = client.patch(f'/api/seo/audits/{audit_a_id}/', {
            'status': 'completed',
            'score': 92,
            'completed_at': completed_ts
        }, format='json')
        assert res_a_update.status_code == status.HTTP_200_OK
        assert res_a_update.data['status'] == 'completed'
        assert res_a_update.data['score'] == 92
        print(f"   [PASS] Audit #{audit_a_id} updated to completed with score 92.")

        # 10. USER A CAN DELETE THEIR OWN AUDIT
        print("\n10. Testing Delete Own Audit (DELETE /api/seo/audits/<user_a_audit_id>/)...")
        temp_audit = SiteAudit.objects.create(project=proj_a, status='failed', error_message='Temporary test error')
        temp_audit_id = temp_audit.id
        res_a_delete = client.delete(f'/api/seo/audits/{temp_audit_id}/')
        assert res_a_delete.status_code == status.HTTP_204_NO_CONTENT
        assert not SiteAudit.objects.filter(id=temp_audit_id).exists()
        print(f"   [PASS] Deleted own audit #{temp_audit_id} successfully (204 No Content).")

        # 11. PROJECT FILTERING WORKS
        print("\n11. Testing Project Filtering (?project_id=...)...")
        proj_a2 = Project.objects.create(owner=user_a, name="Secondary Project", website_url="https://second.et")
        audit_a2 = SiteAudit.objects.create(project=proj_a2, status='completed', score=70)

        res_filter_proj = client.get(f'/api/seo/audits/?project_id={proj_a.id}')
        assert res_filter_proj.status_code == status.HTTP_200_OK
        p_ids = [a['id'] for a in res_filter_proj.data]
        assert audit_a_id in p_ids
        assert audit_a2.id not in p_ids
        print(f"   [PASS] Filter by Project #{proj_a.id} returned only its audits.")

        # 12. CROSS-USER PROJECT FILTERING IS ISOLATED
        print("\n12. Testing Cross-User Project Filter Isolation...")
        res_cross_filter = client.get(f'/api/seo/audits/?project_id={proj_b.id}')
        assert res_cross_filter.status_code == status.HTTP_200_OK
        assert len(res_cross_filter.data) == 0
        print("   [PASS] Querying with another user's project_id returned empty list [].")

        # 13. USER A CAN CREATE AN ISSUE UNDER THEIR OWN AUDIT
        print("\n13. Testing Issue Creation Under User A's Audit...")
        issue_payload = {
            'audit': audit_a_id,
            'issue_type': 'missing_h1',
            'severity': 'critical',
            'title': 'Missing H1 heading tag on landing page',
            'description': 'The homepage is missing a primary H1 heading element.',
            'page_url': 'https://addistech.et/',
            'recommendation': 'Add a clear H1 tag containing relevant primary keywords.'
        }
        res_issue_create = client.post('/api/seo/issues/', issue_payload, format='json')
        assert res_issue_create.status_code == status.HTTP_201_CREATED, f"Failed: {res_issue_create.data}"
        issue_a_id = res_issue_create.data['id']
        assert res_issue_create.data['audit'] == audit_a_id
        assert res_issue_create.data['severity'] == 'critical'
        assert res_issue_create.data['project_name'] == "Addis Tech Portal"
        print(f"   [PASS] Created Issue #{issue_a_id} under Audit #{audit_a_id}.")

        # User B creates an issue under User B's audit
        client.force_authenticate(user=user_b)
        res_b_issue = client.post('/api/seo/issues/', {
            'audit': audit_b_id,
            'issue_type': 'slow_lcp',
            'severity': 'warning',
            'title': 'Largest Contentful Paint exceeds 2.5s',
            'description': 'Main banner image is uncompressed.'
        }, format='json')
        assert res_b_issue.status_code == status.HTTP_201_CREATED
        issue_b_id = res_b_issue.data['id']
        print(f"   [PASS] User B created Issue #{issue_b_id} under Audit #{audit_b_id}.")

        # 14. USER A CANNOT CREATE AN ISSUE UNDER USER B'S AUDIT
        print("\n14. Testing Cross-User Issue Creation Block...")
        client.force_authenticate(user=user_a)
        res_cross_issue_create = client.post('/api/seo/issues/', {
            'audit': audit_b_id, # User B's audit
            'issue_type': 'broken_link',
            'severity': 'notice',
            'title': 'Broken footer link'
        }, format='json')
        assert res_cross_issue_create.status_code == status.HTTP_400_BAD_REQUEST
        print("   [PASS] Blocked with 400 Bad Request (Ownership validation).")

        # 15. USER A CANNOT READ USER B'S AUDIT ISSUE
        print("\n15. Testing Cross-User Issue Read Block (GET /api/seo/issues/<user_b_issue_id>/)...")
        res_cross_issue_get = client.get(f'/api/seo/issues/{issue_b_id}/')
        assert res_cross_issue_get.status_code == status.HTTP_404_NOT_FOUND

        res_a_issues_list = client.get('/api/seo/issues/')
        assert res_a_issues_list.status_code == status.HTTP_200_OK
        iss_ids = [i['id'] for i in res_a_issues_list.data]
        assert issue_a_id in iss_ids
        assert issue_b_id not in iss_ids
        print("   [PASS] Blocked with 404 Not Found on detail, User B issue excluded from list.")

        # 16. USER A CANNOT MODIFY USER B'S AUDIT ISSUE
        print("\n16. Testing Cross-User Issue Modification Block (PATCH /api/seo/issues/<user_b_issue_id>/)...")
        res_cross_issue_patch = client.patch(f'/api/seo/issues/{issue_b_id}/', {'title': 'Tampered title'}, format='json')
        assert res_cross_issue_patch.status_code == status.HTTP_404_NOT_FOUND
        b_iss_obj = AuditIssue.objects.get(id=issue_b_id)
        assert b_iss_obj.title != 'Tampered title'
        print("   [PASS] Blocked with 404 Not Found. Issue record untouched.")

        # 17. USER A CANNOT DELETE USER B'S AUDIT ISSUE
        print("\n17. Testing Cross-User Issue Deletion Block (DELETE /api/seo/issues/<user_b_issue_id>/)...")
        res_cross_issue_delete = client.delete(f'/api/seo/issues/{issue_b_id}/')
        assert res_cross_issue_delete.status_code == status.HTTP_404_NOT_FOUND
        assert AuditIssue.objects.filter(id=issue_b_id).exists()
        print("   [PASS] Blocked with 404 Not Found. Issue record intact.")

        # 18. ISSUE FILTERING BY AUDIT WORKS & CROSS-USER IS ISOLATED
        print("\n18. Testing Issue Filtering (?audit_id=...)...")
        issue_a_2 = AuditIssue.objects.create(
            audit=audit_a2,
            issue_type='meta_description',
            severity=IssueSeverity.NOTICE,
            title='Short meta description'
        )
        res_filter_audit = client.get(f'/api/seo/issues/?audit_id={audit_a_id}')
        assert res_filter_audit.status_code == status.HTTP_200_OK
        audit_iss_ids = [i['id'] for i in res_filter_audit.data]
        assert issue_a_id in audit_iss_ids
        assert issue_a_2.id not in audit_iss_ids
        print(f"   [PASS] Filter by Audit #{audit_a_id} returned only its issues.")

        res_cross_audit_filter = client.get(f'/api/seo/issues/?audit_id={audit_b_id}')
        assert res_cross_audit_filter.status_code == status.HTTP_200_OK
        assert len(res_cross_audit_filter.data) == 0
        print("   [PASS] Cross-user audit_id filter safely returned empty list [].")

        # 19. INVALID SCORE VALUES ARE REJECTED
        print("\n19. Testing Invalid Score Validation (<0 or >100)...")
        for bad_score in [-1, 101, 250]:
            bad_score_res = client.post('/api/seo/audits/', {
                'project': proj_a.id,
                'score': bad_score
            }, format='json')
            assert bad_score_res.status_code == status.HTTP_400_BAD_REQUEST, f"Score {bad_score} was not rejected"
        print("   [PASS] Scores < 0 and > 100 rejected with 400 Bad Request.")

        # 20. CASCADE DELETION WORKS CORRECTLY
        print("\n20. Testing Cascade Deletion (Project -> SiteAudit -> AuditIssue)...")
        assert issue_a_id is not None
        assert SiteAudit.objects.filter(id=audit_a_id).exists()
        assert AuditIssue.objects.filter(id=issue_a_id).exists()

        # Deleting audit_a deletes issue_a
        SiteAudit.objects.get(id=audit_a_id).delete()
        assert not SiteAudit.objects.filter(id=audit_a_id).exists()
        assert not AuditIssue.objects.filter(id=issue_a_id).exists()
        print("   [PASS] Deleting SiteAudit cascaded and deleted associated AuditIssue records.")

        # Deleting project_a2 deletes audit_a2 and issue_a_2
        proj_a2_id = proj_a2.id
        proj_a2.delete()
        assert not SiteAudit.objects.filter(id=audit_a2.id).exists()
        assert not AuditIssue.objects.filter(id=issue_a_2.id).exists()
        print("   [PASS] Deleting Project cascaded and deleted SiteAudit and AuditIssues.")

        print("\n==========================================")
        print("  ALL 20 SITE AUDIT API TESTS PASSED!     ")
        print("==========================================\n")

    finally:
        User.objects.filter(email__in=[email_a, email_b]).delete()

if __name__ == '__main__':
    run_site_audits_tests()
