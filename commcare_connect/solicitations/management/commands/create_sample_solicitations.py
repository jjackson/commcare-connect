import random
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from faker import Faker

from commcare_connect.opportunity.models import DeliveryType
from commcare_connect.organization.models import Organization, UserOrganizationMembership
from commcare_connect.program.models import Program
from commcare_connect.solicitations.models import Solicitation, SolicitationQuestion, SolicitationResponse
from commcare_connect.solicitations.tests.factories import (
    SolicitationWithQuestionsFactory,
    SolicitationWithResponsesFactory,
)
from commcare_connect.users.tests.factories import UserFactory

User = get_user_model()
fake = Faker()


class Command(BaseCommand):
    help = "Creates sample EOI/RFP solicitations and related test data"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=5, help="Number of solicitations to create")
        parser.add_argument(
            "--org_slug", type=str, default="test-program-org", help="Organization slug that will own the programs"
        )
        parser.add_argument(
            "--responding_orgs", type=int, default=3, help="Number of responding organizations to create"
        )
        parser.add_argument("--with_responses", action="store_true", help="Create sample responses to solicitations")
        parser.add_argument("--cleanup", action="store_true", help="Clean up existing sample solicitation data")

    def clean_sample_data(self):
        """Clean up previous sample solicitation data in dependency order"""
        self.stdout.write("Cleaning up previous sample solicitation data...")

        # Delete in reverse dependency order
        deletions = [
            lambda: SolicitationResponse.objects.filter(solicitation__title__icontains="sample").delete(),
            lambda: SolicitationQuestion.objects.filter(solicitation__title__icontains="sample").delete(),
            lambda: Solicitation.objects.filter(title__icontains="sample").delete(),
            # Note: We don't delete Programs/Organizations as they might be used elsewhere
        ]

        for delete in deletions:
            delete()

        self.stdout.write("Cleanup complete.")

    def get_or_create_program_org(self, org_slug):
        """Get or create the organization that will own programs"""
        org, created = Organization.objects.get_or_create(
            slug=org_slug,
            defaults={
                "name": f"{org_slug.title()} Organization",
                "slug": org_slug,
                "program_manager": True,  # This org can create programs
            },
        )

        if created:
            self.stdout.write(f"Created program organization: {org.name}")
            # Create a program manager user for this org
            user = UserFactory(email=f"manager@{org_slug}.com", username=f"{org_slug}_manager")
            UserOrganizationMembership.objects.create(
                user=user, organization=org, role=UserOrganizationMembership.Role.ADMIN, accepted=True
            )
            self.stdout.write(f"Created program manager: {user.email}")
        else:
            self.stdout.write(f"Using existing program organization: {org.name}")

        return org

    def get_or_create_programs(self, org, count=2):
        """Get or create sample programs"""
        programs = []

        # Get or create a default delivery type
        delivery_type, created = DeliveryType.objects.get_or_create(
            name="Digital Health Services", defaults={"name": "Digital Health Services"}
        )
        if created:
            self.stdout.write(f"Created delivery type: {delivery_type.name}")

        program_configs = [
            {
                "name": "Sample Maternal Health Program",
                "slug": "sample-maternal-health",
                "description": "Improving maternal health outcomes in rural communities",
            },
            {
                "name": "Sample Child Nutrition Program",
                "slug": "sample-child-nutrition",
                "description": "Addressing malnutrition in children under 5",
            },
        ]

        for config in program_configs[:count]:
            program, created = Program.objects.get_or_create(
                slug=config["slug"],
                defaults={
                    "name": config["name"],
                    "description": config["description"],
                    "delivery_type": delivery_type,
                    "budget": random.randint(50000, 500000),
                    "currency": "USD",
                    "start_date": datetime.now().date(),
                    "end_date": (datetime.now() + timedelta(days=365)).date(),
                    "organization": org,
                },
            )
            programs.append(program)

            if created:
                self.stdout.write(f"Created program: {program.name}")
            else:
                self.stdout.write(f"Using existing program: {program.name}")

        return programs

    def create_responding_organizations(self, count):
        """Create organizations that will respond to solicitations"""
        orgs = []

        for i in range(count):
            org_slug = f"sample-responder-{i+1}"
            org, created = Organization.objects.get_or_create(
                slug=org_slug,
                defaults={
                    "name": f"Sample Responding Organization {i+1}",
                    "slug": org_slug,
                },
            )

            if created:
                # Create a user for this org
                user = UserFactory(email=f"contact@{org_slug}.com", username=f"{org_slug}_user")
                UserOrganizationMembership.objects.create(
                    user=user, organization=org, role=UserOrganizationMembership.Role.MEMBER, accepted=True
                )
                self.stdout.write(f"Created responding org: {org.name} with user: {user.email}")

            orgs.append(org)

        return orgs

    def create_sample_solicitations(self, programs, count):
        """Create sample solicitations using factories"""
        solicitations = []

        for i in range(count):
            program = random.choice(programs)

            # Choose between EOI and RFP, create with questions
            solicitation_type = random.choice(["eoi", "rfp"])

            # Create solicitation with questions using factory
            solicitation = SolicitationWithQuestionsFactory(
                program=program,
                solicitation_type=solicitation_type,
                status=random.choice(["draft", "active", "active", "active"]),  # Bias toward active
                is_publicly_listed=random.choice([True, True, True, False]),  # Bias toward public
                created_by=program.organization.members.filter(
                    memberships__role=UserOrganizationMembership.Role.ADMIN
                ).first(),
                application_deadline=fake.future_date(end_date="+60d"),
                expected_start_date=fake.future_date(end_date="+90d"),
                expected_end_date=fake.future_date(end_date="+365d"),
            )

            solicitations.append(solicitation)
            self.stdout.write(f"Created solicitation: {solicitation.title}")

        return solicitations

    def create_sample_responses(self, solicitations, responding_orgs):
        """Create sample responses to solicitations using factory logic"""
        responses = []

        for solicitation in solicitations:
            # Random subset of orgs respond to each solicitation
            respondents = random.sample(responding_orgs, k=random.randint(1, min(3, len(responding_orgs))))

            for org in respondents:
                user = org.members.first()
                if not user:
                    continue

                # Generate responses to questions (using same logic as factory)
                question_responses = {}
                for question in solicitation.questions.all():
                    if question.question_type == "file":
                        question_responses[f"question_{question.id}"] = "sample_document.pdf"
                    else:
                        question_responses[f"question_{question.id}"] = fake.text(max_nb_chars=300)

                response = SolicitationResponse.objects.create(
                    solicitation=solicitation,
                    organization=org,
                    submitted_by=user,
                    responses=question_responses,
                    status=random.choice(["submitted", "under_review", "accepted", "rejected"]),
                )

                responses.append(response)
                self.stdout.write(f"Created response from {org.name} to {solicitation.title}")

        return responses

    def create_solicitations_with_responses(self, programs, count, responding_orgs):
        """Create solicitations with responses using the factory"""
        solicitations = []

        for i in range(count):
            program = random.choice(programs)

            # Choose between EOI and RFP, create with questions and responses
            solicitation_type = random.choice(["eoi", "rfp"])

            # Create solicitation with questions and responses using factory
            solicitation = SolicitationWithResponsesFactory(
                program=program,
                solicitation_type=solicitation_type,
                status=random.choice(["draft", "active", "active", "active"]),  # Bias toward active
                is_publicly_listed=random.choice([True, True, True, False]),  # Bias toward public
                created_by=program.organization.members.filter(
                    memberships__role=UserOrganizationMembership.Role.ADMIN
                ).first(),
                application_deadline=fake.future_date(end_date="+60d"),
                expected_start_date=fake.future_date(end_date="+90d"),
                expected_end_date=fake.future_date(end_date="+365d"),
                responses__num_responses=random.randint(1, min(3, len(responding_orgs))),
            )

            solicitations.append(solicitation)
            self.stdout.write(f"Created solicitation with responses: {solicitation.title}")

        return solicitations

    def handle(self, *args, **options):
        count = options["count"]
        org_slug = options["org_slug"]
        responding_orgs_count = options["responding_orgs"]
        with_responses = options["with_responses"]
        cleanup = options["cleanup"]

        if cleanup:
            self.clean_sample_data()

        self.stdout.write("Creating sample solicitation ecosystem...")

        # 1. Get or create the program-owning organization
        program_org = self.get_or_create_program_org(org_slug)

        # 2. Get or create programs under this organization
        programs = self.get_or_create_programs(program_org, count=2)

        # 3. Create responding organizations (if we need responses)
        responding_orgs = []
        if with_responses:
            responding_orgs = self.create_responding_organizations(responding_orgs_count)

        # 4. Create sample solicitations
        if with_responses and responding_orgs:
            # Create solicitations with responses using factory
            solicitations = self.create_solicitations_with_responses(programs, count, responding_orgs)
        else:
            # Create solicitations without responses
            solicitations = self.create_sample_solicitations(programs, count)

        self.stdout.write(
            self.style.SUCCESS(f"Successfully created {len(solicitations)} sample solicitations with full ecosystem!")
        )

        # Print helpful URLs
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("🎉 Sample data created! Try these URLs:")
        self.stdout.write("=" * 50)
        self.stdout.write("📋 Public solicitations list: http://localhost:8000/solicitations/")
        self.stdout.write("🔍 EOIs only: http://localhost:8000/solicitations/eoi/")
        self.stdout.write("📄 RFPs only: http://localhost:8000/solicitations/rfp/")
        self.stdout.write(f"⚙️  Program dashboard: http://localhost:8000/a/{org_slug}/program/")
        self.stdout.write("=" * 50)
