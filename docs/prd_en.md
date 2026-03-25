# Q&A Notification Service PRD

## 1. Document Overview

### 1.1 Background
When inquiry reception is handled manually through storage, admin notification, status management, and completion notice, omissions and duplicates can easily occur. This document defines the product requirements for a simple Q&A notification service that automates inquiry registration and completion notifications.

### 1.2 Goals
- Users can register an inquiry from the web.
- Registered inquiries are automatically stored and immediate notifications are sent to admins.
- Admins can view inquiry status and manage it as `등록됨`, `처리중`, `완료됨`.
- On `완료됨`, both requester and admin receive a completion notification.
- Duplicate inquiries with the same `name + title` combination are not registered.

### 1.3 Success Criteria
- Users can immediately see whether inquiry registration succeeded or failed.
- Admins can check the full inquiry list and current status from the admin page.
- After completion, Notion DB and email notification status are reflected consistently.
- Required-field validation and duplicate prevention reduce invalid data input.

## 2. Users and Scope

### 2.1 Primary Users
- Inquirer: user who submits an inquiry through the public inquiry form
- Admin: operator who views inquiry lists and manages statuses/results

### 2.2 Included Scope
- Public inquiry submission page
- Admin inquiry list/status management page
- n8n registration workflow call on inquiry registration
- n8n completion workflow call on completion processing
- Notion DB storage and status synchronization integration
- Admin and inquirer email notifications
- Adding phone field and basic validation
- Duplicate prevention considering concurrent request scenarios

### 2.3 Excluded Scope
- Separate login for inquirers and self-service inquiry status view
- Complex admin authentication system
- Notification channels other than email
- File attachment upload

## 3. Product Principles and Assumptions

- Inquiry registration is open to everyone without login.
- The admin page assumes minimal access control via password protection instead of a complex auth system.
- `In Progress` status change only updates internal status and persistence, with no additional external notification.
- The completion workflow is called only when status changes to `Completed`.
- Input validation targets practical, standard-level validation used in real implementations.

## 4. User Flows

### 4.1 Inquiry Registration Flow
1. The inquirer enters `name`, `email`, `phone`, `title`, and `body` on the inquiry page.
2. The system validates required fields, whitespace-only inputs, email format, and phone format.
3. When the submit button is clicked, the system calls the registration workflow.
4. The registration workflow checks for duplicates.
5. If not duplicate, it stores the inquiry in Notion DB and sends an email to admin.
6. The system displays registration result to the user.

### 4.2 Admin Processing Flow
1. Admin views the inquiry list on the admin page.
2. Admin checks current status and key details of each inquiry.
3. Admin changes inquiry status to one of `등록됨`, `처리중`, `완료됨`.
4. On `In Progress`, the system persists the status.
5. On `Completed`, the system calls the completion workflow with processing result payload.

### 4.3 Completion Flow
1. The completion workflow sends a result email to the inquirer.
2. The completion workflow sends a completion notification email to the admin.
3. Notion DB updates status and resolution according to `Completed`.

## 5. Functional Requirements

### 5.1 Inquiry Submission Page
- User can input `name`, `email`, `phone`, `title`, and `body`.
- Each field must be validated before submission.
- Duplicate submission must be prevented when the submit button is clicked.
- During processing, user should see an in-progress indication.
- On success, a success message must be shown.
- On failure, a message explaining the reason must be shown.

### 5.2 Input Validation
- `name`, `email`, `phone`, `title`, and `body` are required fields.
- Whitespace-only input is considered invalid.
- Email must pass standard email format validation.
- Phone number must pass standard phone format validation.
- Title and body should not be saved as meaningless empty strings.

### 5.3 Admin Page
- Admin can view inquiry list in up-to-date state.
- Admin can see `name`, `email`, `phone`, `title`, `status`, and `createdAt` for each inquiry in the list.
- Admin can view or enter detailed content and resolution for each inquiry.
- Admin can change inquiry status.
- Status change results should immediately reflect in the UI.

### 5.4 Duplicate Prevention
- Same `name + title` is treated as a duplicate inquiry.
- Duplicate inquiries are not stored.
- Users should be informed when a duplicate registration is rejected.
- The system should be designed so that simultaneous same inquiries are not stored multiple times even when Notion DB responses are slow.

### 5.5 External Workflow Integration
- On inquiry submission, the n8n registration workflow must be called.
- Registration workflow must perform Notion DB storage and admin email delivery.
- On completion, the n8n completion workflow must be called.
- Completion workflow must send requester result email, admin completion email, and update Notion status/resolution.

## 6. Data and State Definitions

### 6.1 Inquiry Data Fields
Each inquiry has at least the following attributes.

| Field | Description |
| --- | --- |
| `id` | Inquiry identifier |
| `name` | Inquirer name |
| `email` | Inquirer email |
| `phone` | Inquirer phone number |
| `title` | Inquiry title |
| `body` | Inquiry body |
| `status` | Inquiry status |
| `resolution` | Resolution or answer content |
| `createdAt` | Creation timestamp |
| `updatedAt` | Last modified timestamp |

### 6.2 Status Definitions

| Status | Description |
| --- | --- |
| `등록됨` | Initial state where the inquiry is successfully accepted |
| `처리중` | In progress after admin review |
| `완료됨` | Finalized result and ready to run completion workflow |

### 6.3 External Integration Events

| Event | Trigger | Purpose |
| --- | --- | --- |
| `Inquiry Registration Request` | When user submits an inquiry | duplicate check, Notion storage, admin email |
| `Completion Processing Request` | When admin sets status to `Completed` | send inquirer email, send admin completion notification, update Notion status/resolution |

## 7. Acceptance Criteria

### 7.1 Inquiry Registration
- Inquiry registration must succeed when all required fields are valid.
- On success, users must see success feedback.
- If inputs are invalid, errors should be displayed before submission.
- If server or workflow error occurs, failure message should be shown.

### 7.2 Duplicate Handling
- If an existing inquiry with same `name + title` exists, new inquiry must not be saved.
- On duplicate registration, admin email and Notion storage should not be duplicated.
- Even with simultaneous requests for the same inquiry, only one record should remain.

### 7.3 Admin Processing
- Admin can view inquiry list and current status.
- If admin changes status to `In Progress`, it must be persisted immediately in storage.
- If admin changes status to `Completed`, the completion workflow must execute.
- After completion, inquirer email, admin completion email, and Notion status update must all be reflected.

## 8. Non-functional Requirements

- User-facing outcomes should provide clear success/failure messages.
- Admin list should have practical readability suitable for real usage within project scope.
- State transitions and workflow invocations should avoid duplicate executions.
- Service structure should stay simple and understandable while meeting requirements.

## 9. Risks and Follow-up Decisions

- Duplicate prevention under concurrent access must be finalized technically during implementation.
- Detailed admin protection method may vary by technology choices.
- Actual Notion property names and n8n workflow input/output schema must be fixed before implementation.
- If these decisions become durable architecture decisions, manage them in separate ADRs.
