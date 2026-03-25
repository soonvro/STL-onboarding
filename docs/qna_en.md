* Is querying an inquirer's own inquiry status after submission considered out of scope?
  -> If no explicit answer is provided, I will guide users only with the registration result, and make status view/manage available only from the admin page.

* Is inquiry submission intended to be available without login?
  -> If no separate answer is provided, I will implement a public inquiry form.

* Should the admin page be implemented without authentication, or should there be at least minimal login/protection?
  -> If no separate answer is provided, I will implement minimum access control at the password-protected page level instead of a complex authentication system.

* Should changing to `In Progress` only update internal status without calling an external workflow, and call the n8n completion workflow only when changing to `Completed`?
  -> If no separate answer is provided, I will also apply status updates to Notion DB for the `In Progress` transition.

* What depth of validation is expected for the optional requirements?
  -> If no separate answer is provided, I will apply practical validation such as required fields, rejecting whitespace-only values, and basic format checks.
