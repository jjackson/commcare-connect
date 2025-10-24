from datetime import timedelta

from django.shortcuts import render
from django.utils import timezone


def get_mock_tasks():
    """Generate comprehensive mock task ticket data."""
    # Set base_date to 2 days ago so all tasks appear recent
    base_date = timezone.now() - timedelta(days=2)

    return [
        {
            "id": 1001,
            "flw_name": "Amina Okafor",
            "flw_username": "amina.okafor@example.com",
            "opportunity": "Reading Glasses Distribution - Nigeria",
            "action_type": "warning",
            "status": "unassigned",
            "created": base_date,
            "assigned_to": "Chidinma Adewale",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2059,
            "source": "audit_failure",
            "priority": "medium",
        },
        {
            "id": 1002,
            "flw_name": "David Martinez",
            "flw_username": "david.martinez@example.com",
            "opportunity": "Education Assessment 2025",
            "action_type": "deactivation",
            "status": "network_manager",
            "created": base_date - timedelta(days=2),
            "assigned_to": "Robert Brown",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2055,
            "source": "audit_failure",
            "priority": "high",
        },
        {
            "id": 1003,
            "flw_name": "Emily Chen",
            "flw_username": "emily.chen@example.com",
            "opportunity": "Health Survey Q4 2025",
            "action_type": "warning",
            "status": "resolved",
            "created": base_date - timedelta(days=5),
            "assigned_to": "Jane Smith",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2061,
            "source": "audit_failure",
            "priority": "low",
        },
        {
            "id": 1004,
            "flw_name": "Michael Williams",
            "flw_username": "michael.williams@example.com",
            "opportunity": "Community Outreach Program",
            "action_type": "deactivation",
            "status": "program_manager",
            "created": base_date - timedelta(days=1),
            "assigned_to": "Sarah Lee",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2058,
            "source": "audit_failure",
            "priority": "high",
        },
        {
            "id": 1005,
            "flw_name": "Jennifer Davis",
            "flw_username": "jennifer.davis@example.com",
            "opportunity": "Health Survey Q4 2025",
            "action_type": "warning",
            "status": "unassigned",
            "created": base_date - timedelta(hours=3),
            "assigned_to": "Jane Smith",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2062,
            "source": "audit_failure",
            "priority": "medium",
        },
        {
            "id": 1006,
            "flw_name": "James Anderson",
            "flw_username": "james.anderson@example.com",
            "opportunity": "Education Assessment 2025",
            "action_type": "warning",
            "status": "resolved",
            "created": base_date - timedelta(days=7),
            "assigned_to": "Robert Brown",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2050,
            "source": "audit_failure",
            "priority": "low",
        },
        {
            "id": 1007,
            "flw_name": "Maria Garcia",
            "flw_username": "maria.garcia@example.com",
            "opportunity": "Health Survey Q4 2025",
            "action_type": "deactivation",
            "status": "network_manager",
            "created": base_date - timedelta(days=3),
            "assigned_to": "Jane Smith",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2056,
            "source": "audit_failure",
            "priority": "high",
        },
        {
            "id": 1008,
            "flw_name": "Robert Taylor",
            "flw_username": "robert.taylor@example.com",
            "opportunity": "Community Outreach Program",
            "action_type": "warning",
            "status": "action_underway",
            "created": base_date - timedelta(hours=12),
            "assigned_to": "Sarah Lee",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2063,
            "source": "audit_failure",
            "priority": "medium",
        },
        {
            "id": 1009,
            "flw_name": "Linda Miller",
            "flw_username": "linda.miller@example.com",
            "opportunity": "Education Assessment 2025",
            "action_type": "deactivation",
            "status": "resolved",
            "created": base_date - timedelta(days=10),
            "assigned_to": "Robert Brown",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2045,
            "source": "audit_failure",
            "priority": "high",
        },
        {
            "id": 1010,
            "flw_name": "Christopher Lee",
            "flw_username": "christopher.lee@example.com",
            "opportunity": "Health Survey Q4 2025",
            "action_type": "warning",
            "status": "program_manager",
            "created": base_date - timedelta(days=1, hours=6),
            "assigned_to": "Jane Smith",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2057,
            "source": "audit_failure",
            "priority": "medium",
        },
        {
            "id": 1011,
            "flw_name": "Patricia Wilson",
            "flw_username": "patricia.wilson@example.com",
            "opportunity": "Community Outreach Program",
            "action_type": "deactivation",
            "status": "network_manager",
            "created": base_date - timedelta(days=4),
            "assigned_to": "Sarah Lee",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2053,
            "source": "audit_failure",
            "priority": "high",
        },
        {
            "id": 1012,
            "flw_name": "Daniel Martinez",
            "flw_username": "daniel.martinez@example.com",
            "opportunity": "Health Survey Q4 2025",
            "action_type": "warning",
            "status": "resolved",
            "created": base_date - timedelta(days=8),
            "assigned_to": "Jane Smith",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2048,
            "source": "audit_failure",
            "priority": "low",
        },
        {
            "id": 1013,
            "flw_name": "Nancy Rodriguez",
            "flw_username": "nancy.rodriguez@example.com",
            "opportunity": "Education Assessment 2025",
            "action_type": "warning",
            "status": "unassigned",
            "created": base_date - timedelta(hours=8),
            "assigned_to": "Robert Brown",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2064,
            "source": "audit_failure",
            "priority": "medium",
        },
        {
            "id": 1014,
            "flw_name": "Steven White",
            "flw_username": "steven.white@example.com",
            "opportunity": "Health Survey Q4 2025",
            "action_type": "deactivation",
            "status": "resolved",
            "created": base_date - timedelta(days=6),
            "assigned_to": "Jane Smith",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2051,
            "source": "audit_failure",
            "priority": "high",
        },
        {
            "id": 1015,
            "flw_name": "Karen Thompson",
            "flw_username": "karen.thompson@example.com",
            "opportunity": "Community Outreach Program",
            "action_type": "warning",
            "status": "action_underway",
            "created": base_date - timedelta(hours=2),
            "assigned_to": "Sarah Lee",
            "created_by": "PM - Michael Chen",
            "audit_session_id": 2065,
            "source": "audit_failure",
            "priority": "low",
        },
    ]


def get_mock_task_detail(task_id):
    """Get detailed mock data for a specific task ticket."""
    tasks = get_mock_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)

    if not task:
        # Return a default task for demo purposes
        task = tasks[0]

    # Add detailed timeline/history with richer scenarios for first few tickets
    now = timezone.now()
    timeline_scenarios = {
        1001: [  # Reading glasses photo quality issue - Last 3 days, newest to oldest
            {
                "timestamp": now - timedelta(hours=6),
                "actor": "AI Assistant",
                "action": "AI Conversation",
                "description": "SMS conversation with worker about training follow-up",
                "icon": "fa-robot",
                "color": "green",
                "display_name": "AI Assistant",
                "conversation": [
                    {
                        "actor": "AI Assistant",
                        "timestamp": now - timedelta(hours=6),
                        "message": (
                            f"Hello {task['flw_name']}! Thank you for completing the Image Capture "
                            "Learn module. I see you scored 95% - great work! Do you have any "
                            "follow-up questions after the training?"
                        ),
                    },
                    {
                        "actor": task["flw_name"],
                        "timestamp": now - timedelta(hours=6),
                        "message": (
                            "Yes, one question - when I take the photo, should the person be smiling "
                            "or have a neutral expression? The module didn't specify."
                        ),
                    },
                    {
                        "actor": "AI Assistant",
                        "timestamp": now - timedelta(hours=6),
                        "message": (
                            "Great question! A neutral expression is preferred so we can clearly see "
                            "how the glasses fit on the face. Smiling can slightly change facial "
                            "features. Natural, relaxed expression works best for verification. "
                            "You're ready to go!"
                        ),
                    },
                ],
            },
            {
                "timestamp": now - timedelta(hours=24),
                "actor": task["flw_name"],
                "action": "Learning Completed",
                "description": "Completed Image Capture learning module (Score: 95%) - Duration: 18 minutes",
                "icon": "fa-check-circle",
                "color": "green",
                "display_name": task["flw_name"],
            },
            {
                "timestamp": now - timedelta(hours=48),
                "actor": task["created_by"],
                "action": "Learning Assigned",
                "description": (
                    "Connect Learn module assigned: Image Capture - Review proper photography "
                    "techniques for glasses fitting documentation"
                ),
                "icon": "fa-graduation-cap",
                "color": "blue",
                "display_name": task["created_by"].split(" - ", 1)[1]
                if " - " in task["created_by"]
                else task["created_by"],
            },
            {
                "timestamp": now - timedelta(hours=60),
                "actor": task["assigned_to"],
                "action": "Commented",
                "description": (
                    "I reviewed the submitted photos. Most 'glasses on face' shots are taken at "
                    "an angle or from too far away. The worker needs to ensure photos are head-on "
                    "from shoulders up to properly verify the glasses fit. I've assigned Learning "
                    "for the Image Capture module."
                ),
                "icon": "fa-comment",
                "color": "gray",
                "display_name": task["assigned_to"].split(" - ", 1)[1]
                if " - " in task["assigned_to"]
                else task["assigned_to"],
            },
        ],
        1002: [  # Warning with quick FLW response
            {
                "timestamp": task["created"],
                "actor": task["created_by"],
                "action": "Created",
                "description": "Action ticket created - minor quality issues detected in audit",
                "icon": "fa-plus-circle",
                "color": "blue",
            },
            {
                "timestamp": task["created"] + timedelta(minutes=5),
                "actor": "System",
                "action": "Warning Sent",
                "description": "Warning notification sent to FLW via SMS and email",
                "icon": "fa-envelope",
                "color": "green",
            },
            {
                "timestamp": task["created"] + timedelta(minutes=8),
                "actor": "System",
                "action": "Notification Sent",
                "description": (
                    f"Network Manager "
                    f"{task['assigned_to'].split(' - ')[1] if ' - ' in task['assigned_to'] else 'assigned'} "
                    f"notified"
                ),
                "icon": "fa-bell",
                "color": "green",
            },
            {
                "timestamp": task["created"] + timedelta(minutes=45),
                "actor": task["flw_name"],
                "action": "FLW Acknowledged",
                "description": (
                    "FLW responded via SMS: 'Understood, will be more careful with photo quality. " "Thank you.'"
                ),
                "icon": "fa-check",
                "color": "green",
            },
            {
                "timestamp": task["created"] + timedelta(hours=1),
                "actor": task["assigned_to"],
                "action": "Commented",
                "description": (
                    "FLW has acknowledged and seems receptive. This is their first warning this "
                    "quarter. Will monitor but no further action needed."
                ),
                "icon": "fa-comment",
                "color": "gray",
            },
            {
                "timestamp": task["created"] + timedelta(hours=1, minutes=5),
                "actor": task["assigned_to"],
                "action": "Status Changed",
                "description": "Status changed to Resolved",
                "icon": "fa-exchange-alt",
                "color": "green",
            },
        ],
        1003: [  # Escalated case with delays
            {
                "timestamp": task["created"],
                "actor": task["created_by"],
                "action": "Created",
                "description": "Action ticket created - pattern of recurring issues detected",
                "icon": "fa-plus-circle",
                "color": "blue",
            },
            {
                "timestamp": task["created"] + timedelta(minutes=3),
                "actor": "System",
                "action": "Pattern Detected",
                "description": "This is the 3rd action ticket for this FLW in 30 days - auto-escalated",
                "icon": "fa-exclamation-circle",
                "color": "red",
            },
            {
                "timestamp": task["created"] + timedelta(minutes=5),
                "actor": "System",
                "action": "Deactivation",
                "description": "User temporarily deactivated due to repeated violations",
                "icon": "fa-ban",
                "color": "red",
            },
            {
                "timestamp": task["created"] + timedelta(minutes=10),
                "actor": "System",
                "action": "Notification Sent",
                "description": (
                    f"Network Manager "
                    f"{task['assigned_to'].split(' - ')[1] if ' - ' in task['assigned_to'] else 'assigned'} "
                    f"notified with escalation flag"
                ),
                "icon": "fa-bell",
                "color": "orange",
            },
            {
                "timestamp": task["created"] + timedelta(hours=3),
                "actor": task["assigned_to"],
                "action": "Commented",
                "description": (
                    "I've attempted to reach the FLW multiple times today but no response. This is "
                    "concerning given the pattern. Will try again tomorrow."
                ),
                "icon": "fa-comment",
                "color": "gray",
            },
            {
                "timestamp": task["created"] + timedelta(days=1),
                "actor": task["assigned_to"],
                "action": "Commented",
                "description": (
                    "Finally connected. FLW dealing with family emergency. However, quality issues "
                    "predate this. We've scheduled a video call next week to review procedures in detail."
                ),
                "icon": "fa-comment",
                "color": "gray",
            },
            {
                "timestamp": task["created"] + timedelta(days=1, minutes=5),
                "actor": task["assigned_to"],
                "action": "Status Changed",
                "description": "Status changed to NM Review - awaiting training completion",
                "icon": "fa-exchange-alt",
                "color": "purple",
            },
        ],
    }

    # Use scenario-specific timeline or default timeline
    if task["id"] in timeline_scenarios:
        task["timeline"] = timeline_scenarios[task["id"]]
        # Add display_name for each timeline item
        for item in task["timeline"]:
            if " - " in item["actor"]:
                item["display_name"] = item["actor"].split(" - ", 1)[1]
            else:
                item["display_name"] = item["actor"]
    else:
        # Default timeline for other tickets
        task["timeline"] = [
            {
                "timestamp": task["created"],
                "actor": task["created_by"],
                "action": "Created",
                "description": "Action ticket created due to audit failure",
                "icon": "fa-plus-circle",
                "color": "blue",
            },
            {
                "timestamp": task["created"] + timedelta(minutes=5),
                "actor": "System",
                "action": "Notification Sent",
                "description": (
                    "Warning notification sent to FLW"
                    if task["action_type"] == "warning"
                    else "User deactivated from opportunity"
                ),
                "icon": "fa-envelope",
                "color": "green",
            },
            {
                "timestamp": task["created"] + timedelta(minutes=10),
                "actor": "System",
                "action": "Notification Sent",
                "description": (
                    f"Network Manager "
                    f"{task['assigned_to'].split(' - ')[1] if ' - ' in task['assigned_to'] else 'assigned'} "
                    f"notified"
                ),
                "icon": "fa-bell",
                "color": "green",
            },
        ]

        if task["status"] in ["nm_review", "pm_review", "resolved", "closed"]:
            task["timeline"].append(
                {
                    "timestamp": task["created"] + timedelta(hours=2),
                    "actor": task["assigned_to"],
                    "action": "Commented",
                    "description": (
                        "I've reviewed this case with the FLW. They acknowledged the issue and "
                        "committed to following proper procedures."
                    ),
                    "icon": "fa-comment",
                    "color": "gray",
                }
            )

        if task["status"] in ["pm_review", "resolved", "closed"]:
            task["timeline"].append(
                {
                    "timestamp": task["created"] + timedelta(days=1),
                    "actor": task["assigned_to"],
                    "action": "Status Changed",
                    "description": "Status changed to PM Review",
                    "icon": "fa-exchange-alt",
                    "color": "orange",
                }
            )

        if task["status"] in ["resolved", "closed"]:
            task["timeline"].append(
                {
                    "timestamp": task["created"] + timedelta(days=1, hours=3),
                    "actor": task["created_by"],
                    "action": "Resolved",
                    "description": "Issue resolved. FLW has been retrained and is now compliant.",
                    "icon": "fa-check-circle",
                    "color": "green",
                }
            )

        # Add display_name for default timeline items
        for item in task["timeline"]:
            if " - " in item["actor"]:
                item["display_name"] = item["actor"].split(" - ", 1)[1]
            else:
                item["display_name"] = item["actor"]

    # Add FLW history (previous tickets) - customize for action 1001
    if task["id"] == 1001:
        task["flw_history"] = [
            {
                "id": task["id"] - 100,
                "date": task["created"] - timedelta(days=60),
                "action_type": "warning",
                "status": "resolved",
                "issue": "Incomplete beneficiary information in forms",
            },
        ]
    else:
        task["flw_history"] = [
            {
                "id": task["id"] - 100,
                "date": task["created"] - timedelta(days=45),
                "action_type": "warning",
                "status": "resolved",
                "issue": "Photo quality issues",
            },
            {
                "id": task["id"] - 200,
                "date": task["created"] - timedelta(days=90),
                "action_type": "warning",
                "status": "resolved",
                "issue": "Incomplete form submissions",
            },
        ]

    # Add notification details
    if task["action_type"] == "warning":
        task["notification"] = {
            "recipient": task["flw_name"],
            "subject": "Quality Assurance Notice - Action Required",
            "message": (
                f"Dear {task['flw_name']},\n\n"
                f"Our quality assurance team has identified areas for improvement in your recent "
                f"work on {task['opportunity']}. Please review the audit session details and "
                f"ensure compliance with program standards.\n\n"
                f"Audit Session: #{task['audit_session_id']}\n\n"
                f"Best regards,\nProgram Management Team"
            ),
            "sent_at": task["created"] + timedelta(minutes=5),
        }
    else:
        task["notification"] = {
            "recipient": task["flw_name"],
            "subject": "Account Status Update - Temporary Deactivation",
            "message": (
                f"Dear {task['flw_name']},\n\n"
                f"Due to quality assurance findings, your access to {task['opportunity']} has "
                f"been temporarily suspended pending review. Your Network Manager has been "
                f"notified and will be in touch.\n\n"
                f"Audit Session: #{task['audit_session_id']}\n\n"
                f"For questions, please contact your Network Manager.\n\n"
                f"Best regards,\nProgram Management Team"
            ),
            "sent_at": task["created"] + timedelta(minutes=5),
        }

    return task


def tasks_list(request):
    """Display list of all task tickets with filtering."""
    tasks = get_mock_tasks()

    # Calculate statistics
    stats = {
        "total": len(tasks),
        "unassigned": len([t for t in tasks if t["status"] == "unassigned"]),
        "network_manager": len([t for t in tasks if t["status"] == "network_manager"]),
        "program_manager": len([t for t in tasks if t["status"] == "program_manager"]),
        "action_underway": len([t for t in tasks if t["status"] == "action_underway"]),
        "resolved": len([t for t in tasks if t["status"] == "resolved"]),
    }

    # Get filter parameters
    status_filter = request.GET.get("status", "all")
    action_type_filter = request.GET.get("action_type", "all")

    # Apply filters
    if status_filter != "all":
        tasks = [t for t in tasks if t["status"] == status_filter]
    if action_type_filter != "all":
        tasks = [t for t in tasks if t["action_type"] == action_type_filter]

    # Get unique values for filter dropdowns
    statuses = sorted({t["status"] for t in get_mock_tasks()})
    action_types = sorted({t["action_type"] for t in get_mock_tasks()})

    context = {
        "tasks": tasks,
        "stats": stats,
        "statuses": statuses,
        "action_types": action_types,
        "selected_status": status_filter,
        "selected_action_type": action_type_filter,
    }

    return render(request, "tasks/tasks_list.html", context)


def task_detail_streamlined(request, task_id):
    """Streamlined View: Task-focused interface for assigning and contacting."""
    task = get_mock_task_detail(task_id)

    context = {
        "task": task,
        "prototype_name": "Streamlined View",
        "prototype_description": "Simple task-focused interface: assign or contact",
    }

    return render(request, "tasks/task_detail_streamlined.html", context)
