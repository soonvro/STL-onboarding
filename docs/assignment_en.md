# Onboarding Project

## 📅 Duration
- **2026.03.19 ~ 2026.03.23**

## 📋 Topic and Requirements
Implement a **simple Q&A notification service** that automatically stores and notifies after an inquiry is submitted.

### 🌐 Web Application

- Inquiry submission page
  - Supports input for name, email, title, and body
  - Provides a submit button
  - Shows submission result to the user
  - Calls the n8n registration workflow when the submit button is clicked

- Admin page
  - Supports inquiry list view
  - Shows the status of each inquiry
  - States: `Registered`, `In Progress`, `Completed`
  - Allows status changes
  - Calls n8n completion workflow when status changes to `Completed`

### ⚙️ n8n

- Inquiry registration workflow
  - Save inquiry data to Notion DB
  - Send email to admin
  - Treat same `name + title` as a duplicate inquiry
  - Duplicate inquiries must not be registered

- Completion workflow
  - Send result email to requester
  - Send completion notification email to admin
  - Update status and resolution in Notion DB

> **📝 Note**
> You may freely choose technologies and service structure as long as the requirements are satisfied.

## References
- [n8n homepage](https://n8n.io/)
- [Notion API documentation](https://developers.notion.com/)

## 🚀 Optional Extensions
*You may implement these if you wish.*

1. **Improved duplicate submission handling**
   - Prevent duplicate registration when the same inquiry arrives concurrently, even if Notion DB is slow.

2. **Input validation and additional field**
   - Add a **phone number** field to the inquiry form.
   - Implement **validation** for name / email / phone / title / body.
