import random
from datetime import datetime, timedelta, timezone

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone as djtimezone
from faker import Faker

from commcare_connect.organization.models import Organization, UserOrganizationMembership
from commcare_connect.program.models import Program
from commcare_connect.program.tests.factories import ProgramFactory
from commcare_connect.opportunity.models import DeliveryType
from commcare_connect.solicitations.models import (
    Solicitation,
    SolicitationQuestion,
    SolicitationResponse,
)
from commcare_connect.users.tests.factories import UserFactory, OrganizationFactory

User = get_user_model()
fake = Faker()


class Command(BaseCommand):
    help = "Creates sample EOI/RFP solicitations and related test data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count", 
            type=int, 
            default=5, 
            help="Number of solicitations to create"
        )
        parser.add_argument(
            "--org_slug", 
            type=str, 
            default="test-program-org",
            help="Organization slug that will own the programs"
        )
        parser.add_argument(
            "--responding_orgs", 
            type=int, 
            default=3,
            help="Number of responding organizations to create"
        )
        parser.add_argument(
            "--with_responses", 
            action="store_true",
            help="Create sample responses to solicitations"
        )
        parser.add_argument(
            "--cleanup", 
            action="store_true",
            help="Clean up existing sample solicitation data"
        )

    def clean_sample_data(self):
        """Clean up previous sample solicitation data in dependency order"""
        self.stdout.write("Cleaning up previous sample solicitation data...")
        
        # Delete in reverse dependency order
        deletions = [
            lambda: SolicitationResponse.objects.filter(
                solicitation__title__icontains="sample"
            ).delete(),
            lambda: SolicitationQuestion.objects.filter(
                solicitation__title__icontains="sample"
            ).delete(),
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
            }
        )
        
        if created:
            self.stdout.write(f"Created program organization: {org.name}")
            # Create a program manager user for this org
            user = UserFactory(
                email=f"manager@{org_slug}.com",
                username=f"{org_slug}_manager"
            )
            UserOrganizationMembership.objects.create(
                user=user,
                organization=org,
                role=UserOrganizationMembership.Role.ADMIN,
                accepted=True
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
            name="Digital Health Services",
            defaults={"name": "Digital Health Services"}
        )
        if created:
            self.stdout.write(f"Created delivery type: {delivery_type.name}")
        
        program_configs = [
            {
                "name": "Sample Maternal Health Program",
                "slug": "sample-maternal-health",
                "description": "Improving maternal health outcomes in rural communities"
            },
            {
                "name": "Sample Child Nutrition Program", 
                "slug": "sample-child-nutrition",
                "description": "Addressing malnutrition in children under 5"
            }
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
                }
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
                }
            )
            
            if created:
                # Create a user for this org
                user = UserFactory(
                    email=f"contact@{org_slug}.com",
                    username=f"{org_slug}_user"
                )
                UserOrganizationMembership.objects.create(
                    user=user,
                    organization=org,
                    role=UserOrganizationMembership.Role.MEMBER,
                    accepted=True
                )
                self.stdout.write(f"Created responding org: {org.name} with user: {user.email}")
            
            orgs.append(org)
        
        return orgs

    def create_sample_solicitations(self, programs, count):
        """Create sample solicitations"""
        solicitations = []
        
        solicitation_templates = [
            {
                "type": "eoi",
                "title_suffix": "Expression of Interest",
                "description": "We are seeking qualified local organizations to partner with us in delivering {focus} services to underserved communities. This Expression of Interest will help us identify potential partners for our upcoming program.",
                "questions": [
                    "Describe your organization's experience working with {target_population}",
                    "What is your organization's approach to community engagement?",
                    "How many field workers can your organization deploy?",
                    "Upload your organization's registration certificate",
                    "What geographical areas does your organization currently serve?",
                ]
            },
            {
                "type": "rfp", 
                "title_suffix": "Request for Proposals",
                "description": "Following our Expression of Interest process, we invite selected organizations to submit detailed proposals for implementing {focus} interventions. This RFP outlines specific requirements and deliverables.",
                "questions": [
                    "Provide a detailed implementation timeline",
                    "Submit your detailed budget breakdown",
                    "Describe your quality assurance processes",
                    "Upload supporting documentation (licenses, certifications, etc.)",
                    "How will you measure and report on program outcomes?",
                    "What risks do you anticipate and how will you mitigate them?",
                ]
            }
        ]
        
        focuses = ["maternal health", "child nutrition", "vaccination campaigns", "community health screening"]
        target_populations = ["pregnant women", "children under 5", "rural communities", "vulnerable families"]
        
        for i in range(count):
            program = random.choice(programs)
            template = random.choice(solicitation_templates)
            focus = random.choice(focuses)
            target_pop = random.choice(target_populations)
            
            # Create solicitation
            solicitation = Solicitation.objects.create(
                title=f"Sample {focus.title()} - {template['title_suffix']}",
                description=template["description"].format(
                    focus=focus,
                    target_population=target_pop
                ),
                target_population=target_pop,
                scope_of_work=f"Implement {focus} interventions including community outreach, service delivery, and data collection",
                solicitation_type=template["type"],
                status=random.choice(["draft", "active", "active", "active"]),  # Bias toward active
                is_publicly_listed=random.choice([True, True, True, False]),  # Bias toward public
                program=program,
                created_by=program.organization.members.filter(
                    memberships__role=UserOrganizationMembership.Role.ADMIN
                ).first(),
                application_deadline=fake.future_date(end_date='+60d'),
                estimated_scale=f"{fake.random_int(min=1000, max=50000)} {target_pop}",
                expected_start_date=fake.future_date(end_date='+90d'),
                expected_end_date=fake.future_date(end_date='+365d'),
            )
            
            # Create questions for this solicitation
            for idx, question_text in enumerate(template["questions"]):
                question_type = "file" if "upload" in question_text.lower() else "textarea"
                
                SolicitationQuestion.objects.create(
                    solicitation=solicitation,
                    question_text=question_text.format(
                        target_population=target_pop,
                        focus=focus
                    ),
                    question_type=question_type,
                    is_required=True,
                    order=idx + 1
                )
            
            solicitations.append(solicitation)
            self.stdout.write(f"Created solicitation: {solicitation.title}")
        
        return solicitations

    def create_sample_responses(self, solicitations, responding_orgs):
        """Create sample responses to solicitations"""
        responses = []
        
        for solicitation in solicitations:
            # Random subset of orgs respond to each solicitation
            respondents = random.sample(
                responding_orgs, 
                k=random.randint(1, min(3, len(responding_orgs)))
            )
            
            for org in respondents:
                user = org.members.first()
                if not user:
                    continue
                
                # Generate responses to questions
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
                    status=random.choice(["submitted", "under_review", "accepted", "rejected"])
                )
                
                responses.append(response)
                self.stdout.write(f"Created response from {org.name} to {solicitation.title}")
        
        return responses

    def handle(self, *args, **options):
        count = options["count"]
        org_slug = options["org_slug"]
        responding_orgs_count = options["responding_orgs"]
        with_responses = options["with_responses"]
        cleanup = options["cleanup"]

        if cleanup:
            self.clean_sample_data()

        self.stdout.write(f"Creating sample solicitation ecosystem...")

        # 1. Get or create the program-owning organization
        program_org = self.get_or_create_program_org(org_slug)

        # 2. Get or create programs under this organization
        programs = self.get_or_create_programs(program_org, count=2)

        # 3. Create responding organizations (if we need responses)
        responding_orgs = []
        if with_responses:
            responding_orgs = self.create_responding_organizations(responding_orgs_count)

        # 4. Create sample solicitations
        solicitations = self.create_sample_solicitations(programs, count)

        # 5. Create sample responses (if requested)
        if with_responses and responding_orgs:
            self.create_sample_responses(solicitations, responding_orgs)

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created {len(solicitations)} sample solicitations with full ecosystem!"
            )
        )
        
        # Print helpful URLs
        self.stdout.write("\n" + "="*50)
        self.stdout.write("🎉 Sample data created! Try these URLs:")
        self.stdout.write("="*50)
        self.stdout.write("📋 Public solicitations list: http://localhost:8000/solicitations/")
        self.stdout.write("🔍 EOIs only: http://localhost:8000/solicitations/eoi/")
        self.stdout.write("📄 RFPs only: http://localhost:8000/solicitations/rfp/")
        self.stdout.write(f"⚙️  Program dashboard: http://localhost:8000/a/{org_slug}/program/")
        self.stdout.write("="*50)

