In company I work for we have this fabulous process:
1. in jira-cloud we track timesheets
2. at the end of the month we export timesheets to PDF
    1. send to invoicing dept + to my manager
    2. send an email to my accountant to issue an invoice with the number of hours worked
3. recieve an "approved" email from manager, save the PDF of that email
4. merge the 3 PDFs into one PDF in specific order: invoice + timesheet + approved email
5. send the merged PDF to the accounting of the company + to my manager

I use gmail to send emails, and I want to automate steps 2-5 as much as possible. I want be in the loop always - e.g. a message to Whatsapp or Telegram to approve ANY automated action.


1. i will export timesheet manually to PDF (step 2) - save it to a folder.
2. automation will pick-up, process - get an approve via message - and send emails.
3. automation will listen for "approved" email from manager (step 3) - save the PDF of that email to the same folder.
4. automation will listen for response email from my accountant with issued invoice PDF - save it to the same folder.
5. when all 3 PDFs are in the folder - automation will merge them in specific order
6. automation will get an approve via message - send the merged PDF to accounting and my manager

* For all of this we use gmail to send/recieve emails.
* All steps should be traced in the messenger app we choose.
* We can use an LLM by OpenAI or a Google one for semantic understanding / categorization of emails if needed. We should pick something cost-effective and reliable.