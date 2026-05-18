#### Introduction

Workflow is the component of BillTrak that allows your company to determine the sequence of events needed to process invoices. Workflow is configured to follow the events that occur when your company processes invoices manually. Manual processing includes auditing invoices, noting disputes on payment amounts, applying credits and debits from previous invoices, and reconciling all of these amounts so that payment can be made. Workflow supports invoice processing from receipt through payment completion.

Workflow applies to both invoices and transactions. An **invoice** is the bill that a billing carrier submits to another carrier using its network. A **transaction** is the set of financial components associated with an invoice, such as invoice current due amount plus any disputes, credit and debit reconciliation, and overpayments from previous invoices.

This document describes the process by which TEOCO and the client create a custom workflow configuration. This document also defines the baseline BillTrak workflow configuration, including best practices to enable efficient invoice processing and customization considerations.

BillTrak provides clients the flexibility to design, with TEOCO, their own custom invoice and transaction workflows. In addition, the client may reconfigure their workflow when business processes change.

#### Workflow Design Process

During the implementation process, TEOCO works with the client to identify their current invoice management process and how this process can be configured in BillTrak.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<tbody>
<tr>
<td>Analyze Current Process</td>
</tr>
<tr>
<td><p>The first step in workflow design is to identify the current invoice management process, from invoice receipt through to vendor payment confirmation. The TEOCO Implementation Manager partners with the client to identify all components of the current process, including:</p>
<ul>
<li><p><strong>Process Steps</strong> – Points within the process when an action, or set of actions, are performed on the invoice. For each step, clients should specify:</p>
<ul>
<li><p>Entrance criteria</p></li>
<li><p>Actions that <em>mus</em>t be performed; actions that <em>may</em> be performed</p></li>
<li><p>Exit criteria</p></li>
<li><p>The next possible step or steps, and what determining factors should be used when there are multiple possible steps</p>
<p><u>Example</u>: During the Invoice Review step, the auditor must perform the specified set of audits based on account type and vendor, record disputable charges, notify the vendor of disputed charges, identify dispute credits and their source dispute, and create a vendor payment voucher. In addition, the auditor may generate a dispute report. The auditor must print and deliver the payment voucher to their supervisor in order for the Invoice Review process to be complete.</p></li>
</ul></li>
<li><p><strong>Work Assignment</strong> – For each processing step, identify how the work is assigned. For each step, clients should specify:</p>
<ul>
<li><p>To which users or groups the work is assigned</p></li>
<li><p>Secondary/default user assignments</p></li>
<li><p>The criteria used to identify to whom the work is assigned</p>
<p><u>Example</u>: Invoices in the Invoice Review step are assigned to individual auditors based on the invoice vendor and account type. Invoices for unassigned accounts are given to the supervisor as a default.</p>
<p><u>Example</u>: Payment Vouchers are assigned to supervisors based on submitting auditor. Vouchers are assigned to an alternate supervisor when the assigned supervisor is out of the office.</p></li>
</ul></li>
</ul></td>
</tr>
<tr>
<td><ul>
<li><p><strong>Processing Controls</strong> – Points within the process where work is controlled, either through an approval step or second-level review. Processing controls should include:</p>
<ul>
<li><p>Who is performing the approval or second-level review</p></li>
<li><p>What occurs when the reviewer accepts or rejects the reviewed work</p></li>
</ul></li>
</ul>
<blockquote>
<p><u>Example</u>: Payment vouchers are approved by a supervisor, manager, or director based on the payment amount. Approved vouchers are signed and submitted to the A/P department for payment; rejected vouchers are returned to the submitting auditor for further work.</p>
</blockquote></td>
</tr>
<tr>
<td><strong>Define Custom BillTrak Workflow</strong></td>
</tr>
<tr>
<td><p>The TEOCO Implementation Manager schedules a meeting at the client site. The TEOCO Implementation Manager leads the client implementation team in:</p>
<ul>
<li><p>Confirming the client’s current invoice management process and identifies areas for increased efficiencies</p></li>
<li><p>Reviewing of the BillTrak baseline workflow at a detailed level</p></li>
<li><p>Identifying ways in which the baseline workflow can be customized to capture the client’s current process while taking advantage of BillTrak automated processes</p></li>
</ul>
<p>During this visit, the Implementation Manager also gathers requirements for other system configurations, such as user security settings and automatic audits, using the Configuration Questionnaire.</p></td>
</tr>
<tr>
<td><strong>Document Custom Configuration</strong></td>
</tr>
<tr>
<td><p>The TEOCO Implementation Manager provides a formal document, the Configuration document, describing the client’s custom application configuration.</p>
<p>The client provides written approval or specifies updates that are required to meet their approval.</p>
<p>The Configuration document contains the proposed workflow, including:</p>
<ul>
<li><p>Invoice Workflow Diagram</p></li>
<li><p>Invoice workflow state descriptions, including: actions performed, user assignments, and application functions enabled</p></li>
<li><p>Transaction Workflow Diagram</p></li>
</ul>
<p>Transaction workflow state descriptions, including: actions performed, user assignments, and application functions enabled</p></td>
</tr>
<tr>
<td><strong>Configure and Test Workflow</strong></td>
</tr>
<tr>
<td><p>TEOCO configures BillTrak as specified in the Configuration Worksheet.</p>
<p>TEOCO tests the configuration to ensure that it properly functions and meets the business requirements as defined during the onsite visit.</p></td>
</tr>
<tr>
<td><strong>Maintain Workflow</strong></td>
</tr>
<tr>
<td><p>TEOCO includes the custom application configuration in the product installation. The TEOCO Trainer provides instruction on configuring and maintaining workflow during the BillTrak Administrator course. As part of their user acceptance testing, the client verifies that the custom workflow meets their business needs. The Implementation Manager and TEOCO’s Technical Support team provide client assistance during the user acceptance testing, which includes answering workflow questions and troubleshooting issues. The client, with the assistance of the Implementation Manager, updates workflow as required for transitioning BillTrak into production.</p>
<p>Upon product acceptance, the client assumes responsibility for maintaining their custom workflow. TEOCO provides the client a soft copy of the Configuration document so that all future workflow updates can be documented. The TEOCO Account Manager and Client Technical Support team provide workflow update assistance as needed. TEOCO also offers workflow analysis and reconfiguration as Business Process Consulting.</p></td>
</tr>
</tbody>
</table>

The following table provides a detailed list of invoice workflow states included in the baseline workflow configuration.

<table style="width:100%;">
<colgroup>
<col style="width: 16%" />
<col style="width: 42%" />
<col style="width: 41%" />
</colgroup>
<thead>
<tr>
<th>Workflow State</th>
<th>Purpose</th>
<th>Best Practices and Considerations</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Initial<br />
</strong>(System)</td>
<td>During this transitory system state manually entered invoices and electronic invoices enter the BillTrak invoice workflow.</td>
<td>This is a required state.</td>
</tr>
<tr>
<td><strong>Pre-Audit<br />
</strong>(System)</td>
<td>During this optional transitory state, a number of checks are run on the invoice to determine if it is an active BAN, it includes the CSR, includes the customizable BAN and/or Invoice Circuit Master information required for account coding, and is not a duplicate invoice.</td>
<td>Invoices not meeting all of the checks can be routed to New BAN s or a custom pre-audit review state (e.g., Inactive BANs, No CSR, Update ICM Settings, Potential Duplicates) for completion, and then returned to the Pre-Audit state to continue processing. Invoices that pass all of the checks proceed to Auto recurring Exceptions.</td>
</tr>
<tr>
<td><strong>Customizable Pre-Audit Review States</strong> (Review)</td>
<td>During these optional review states, invoices that failed one or more of the Pre-Audit checks (except new BANs) can be verified as valid and complete. Optional states include: <strong>Inactive BANs</strong>, <strong>No CSR</strong>, <strong>Update ICM Settings</strong>, and <strong>Potential Duplicates</strong>.</td>
<td>It is a best practice to create review states to address invoices that do not pass one or more of the <strong>Pre-Audit</strong> checks to ensure that only valid invoices proceed through workflow and that the invoices contain the necessary custom information required for account coding (e.g., BAN Category 1 &amp; 2, Circuit Category 1 &amp; 2). Valid invoices should transition back to the <strong>Pre-Audit</strong> workflow state to ensure that all checks are run. Invalid invoices should transition to the <strong>Rejected Invoices</strong> workflow state.</td>
</tr>
<tr>
<td><strong>New BANs<br />
</strong>(Review)</td>
<td>During this required review state electronic invoices where BillTrak has created the new BAN record are staged. BAN staging includes: verification of BAN, updating the BAN status, Vendor/Vendor Location assignment, and population of custom BAN-level fields.</td>
<td><p>It is a best practice to assign new accounts to a different user/group than is assigned to review rejected invoices.</p>
<p>It is a best practice to require entry of custom fields, such as those used for account coding, before exiting this workflow state.</p></td>
</tr>
<tr>
<td><strong>Rejected Invoices<br />
</strong>(Review)</td>
<td><p>During this optional state, unrecognized invoices are confirmed as valid or invalid. Valid invoices are transitioned back into workflow, invalid invoices are transitioned to the Invalid Invoices invalid final state.</p>
<p>Invoices are typically transitioned to this state from <strong>Initial</strong>, <strong>New BANs</strong>, one of the customizable pre-audit review states (e.g., <strong>Potential Duplicates</strong>), and <strong>Post-Audit</strong>.</p></td>
<td><p>For clients interested in inserting a control on an invoice’s rejection, it is a best practice to include this workflow state.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>Does your business process require a second-level review of rejected invoices?</p></li>
<li><p>At which points in your business process could an invoice be rejected?</p></li>
<li><p>Is the user/group who verifies new BANs the same user/group that would provide the second-level review of rejected invoices?</p></li>
<li><p>Is the user/group who verifies an invoice’s validity during audit the same user/group that would provide the second-level review of rejected invoices?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>Invalid Invoices<br />
</strong>(System)</td>
<td>This is an invalid final state for invoices that the client identifies as invalid. An invoice is removed from visible workflow after it enters this state.</td>
<td><p>It is a best practice to move rejected invoices out of visible workflow, ensuring that rejected invoice amounts are not included in reporting. However, in order to file a dispute for the full invoice amount, it would have to process through workflow to closure.</p>
<p><u>Considerations</u>:</p>
<ul>
<li><p>How do you manage misdirected invoices and invoices received on obsolete accounts?</p></li>
<li><p>Do you want rejected invoice amounts included in your report results?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>Auto Recurring Exceptions<br />
</strong>(System)</td>
<td>During this optional system state the Auto Recurring Exceptions executable creates an exception for every instance of a recurring manual dispute appearing on the most recent previous invoice for the BAN.</td>
<td><p>For clients interested in using the BillTrak recurring manual disputes feature, it is a best practice to run all valid invoices through Recurring Manual Disputes. This state should be configured to run prior to Auto Audit.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>Do you create manual disputes?</p></li>
<li><p>Do you file the same disputes month after month on the same BANs?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>AutoReconcile<br />
</strong>(System)</td>
<td><p>During this optional system state the Auto Reconcile executable can be configured to one or both of the following:</p>
<ul>
<li><p><strong>Accept all adjustments not in current due</strong> <strong>appearing on the invoice</strong>. Designed for use on small dollar invoices that are to be routed to Auto Submit without auditor review.</p></li>
<li><p><strong>Auto match vendor payments to BTP payments</strong> to streamline payment reconciliation activities.</p></li>
</ul>
<p>Invoices reside in this state until the Auto Reconcile process is run. Auto Reconcile is scheduled to run at timed intervals by the DataLoader Administrator. BillTrak does not accept adjustments or match payments when an invoice is manually transitioned from this state.</p>
<p>Invoices typically transition to an Auto Submit system state from Auto Reconcile. This is an optional state.</p></td>
<td><p>Auto Reconcile should be scheduled to run immediately prior to Auto Audit.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>Will your company use the payment matching and outstanding claims balance functionality in BillTrak?</p></li>
<li><p>[something about accepting adj to support auto submit/process low dollar invoices w/out user intervention]</p></li>
</ul></td>
</tr>
<tr>
<td><strong>Auto Audit<br />
</strong>(System)</td>
<td><p>During this optional system state, the Auto Audit executable runs the configured preliminary edits on all invoices, and the BillTrak audits on all invoices meeting the specified criteria.</p>
<p><strong>Preliminary edits</strong> are used to identify invoice anomalies, using client defined thresholds, warranting further auditor analysis. Preliminary edit examples include:</p>
<ul>
<li><p>Invoice Current Due amount increases/decreases by more than 10%</p></li>
<li><p>Invoice contains a credit or debit adjustment greater than the threshold amount</p></li>
</ul>
<p><strong>Auto audits</strong> are BillTrak audits that automatically run on the applicable invoices prior to user review to increase efficiency.</p></td>
<td><p>For clients who would like to increase auditor efficiency by flagging invoices for further analysis for reasons other than audit results, it is a best practice to run the preliminary edits along with the BillTrak audits during the Auto Audit workflow state.</p>
<p><u>Preliminary Edit Considerations:</u></p>
<ul>
<li><p>What invoice anomalies merit auditor attention?</p></li>
<li><p>What are acceptable thresholds for the preliminary edits (e.g. credit and debit adjustment amounts)?</p></li>
</ul>
<p>It is a best practice to run all valid invoices through Auto Audit, provided that the client has configured automated audits to run only on:</p>
<ul>
<li><p>Invoices containing the audited charges</p></li>
<li><p>Invoices from vendors where the audited charge is eligible for dispute</p></li>
<li><p>Charges where the required interface data, such as circuit inventory, is loaded into BillTrak</p></li>
</ul>
<p><u>Auto Audit Considerations:</u></p>
<ul>
<li><p>Are there any circumstances in which a valid invoice should not be audited?</p></li>
<li><p>Are there any circumstances in which an invoice should be rejected based on audit results (e.g. fails Valid ACNA audit)?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>Pending Augmentation<br />
</strong>(System)</td>
<td><p>During this optional state the AutoAction executable performs the configured circuit augmentation actions on all invoices meeting the specified criteria. This state is used to support batch processing for circuit augmentation actions such as circuit matching.</p>
<p>Invoices reside in this state until the AutoAction process is run. AutoAction is scheduled to run at timed intervals by the DataLoader Administrator. BillTrak does not perform the specified actions when an invoice is manually transitioned from this state.</p>
<p>Invoices typically transition to an AutoAudit system state from Pending Augmentation.</p></td>
<td><p>To ensure that audits generate accurate results, AutoAction should be configured to run prior to AutoAudit.</p>
<p>The AutoAction executable can be run from other system workflow states. TEOCO can create custom invoice or transaction system workflow states to support custom batch action processing requests. Please review the BillTrak Administrator Guide, “Chapter 17: Action Framework,” for more detail.</p></td>
</tr>
<tr>
<td><strong>Post Audit<br />
</strong>(System)</td>
<td>During this optional transitory state, invoices are checked for presence of one or more exceptions generated by a preliminary edit or auto audit. Invoices with no exceptions can be routed to Auto Submit, where a payment request is automatically generated without user intervention. Invoices with exceptions are routed to the Review state.</td>
<td>It is a best practice to use Post-Audit to separate invoices requiring user review from invoices that can be automatically paid.</td>
</tr>
<tr>
<td><strong>Review<br />
</strong>(Review)</td>
<td><p>During this review state auditors perform the majority of their invoice processing, including: analyze Auto Recurring Dispute/Preliminary Edit/Auto Audit results, perform additional manual audits, dispute invoice charges, reconcile credits and debits appearing on the invoice, create a payment transaction, assign account codes to the transaction, and submit the transaction.</p>
<p>Listed below are some of the options for auditor review states:</p>
<ul>
<li><p>Invoices where <strong>no exceptions</strong> are generated during Auto Recurring Exceptions, Preliminary Edits, and Auto Audit</p></li>
<li><p>Invoices where <strong>exceptions</strong> are generated during Auto Recurring Exceptions, Preliminary Edits, and Auto Audit</p></li>
<li><p>Invoices containing <strong>OC&amp;Cs</strong></p></li>
<li><p>Invoices containing <strong>Adjustments</strong></p></li>
<li><p>Invoices with a <strong>$0 balance</strong> or <strong>credit balance</strong></p></li>
<li><p>Invoice with <strong>payment due within 10 days</strong></p></li>
</ul></td>
<td><p>While the baseline solution identifies two auditor review states based on audit run results, BillTrak can be configured to distribute invoices to any number of auditor review states based on client-defined characteristics and priorities.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>How do you prioritize auditor work?</p></li>
<li><p>Based on their experience, would your auditor team benefit from having invoices divided into separate working folders? If so, based on which invoice characteristics?</p>
<ul>
<li><p>By audit results</p></li>
<li><p>By Vendor</p></li>
<li><p>By Invoice Amount</p></li>
<li><p>By custom field</p></li>
<li><p>Other</p></li>
</ul></li>
<li><p>How many review folders are manageable?</p></li>
<li><p>Based on which characteristics are invoices assigned to an individual auditor or audit team?</p>
<ul>
<li><p>By Vendor or BAN</p></li>
<li><p>By Account Type</p></li>
<li><p>By custom field</p></li>
<li><p>Other</p></li>
</ul></li>
<li><p>Is the auditor responsible for account coding the payment transaction prior to submitting it for approval, or do you want BillTrak to automatically account Code the payment transaction upon submission?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>Auto Submit<br />
</strong>(System)</td>
<td>During this system state invoices are automatically submitted for payment without auditor intervention. This state is used only for those invoices that have been identified as small dollar or as not requiring review.</td>
<td><p>To reduce time spent analyzing invoices with little or no potential for disputable charges, it is a best practice to use Auto Submit.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>Under what circumstances is an invoice deemed to be not worthy of review? (e.g. below a certain current due amount, not containing OC&amp;Cs, not containing Adjustments)</p></li>
<li><p>Are you comfortable processing some invoices without user intervention?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>Transaction Processing</strong> (System)</td>
<td>During this system state invoices are placed on hold while their associated transactions are processed through the transaction workflow. BillTrak releases an invoice from this state upon transaction rejection or transaction closure.</td>
<td>This is a required state.</td>
</tr>
<tr>
<td><strong>Invoices With Rejected Transactions<br />
</strong>(Review)</td>
<td>During this review state auditors perform additional auditing, disputing, and reconciliation on the invoice associated with the rejected transaction. Since a rejected transaction cannot be updated or re-submitted, a new transaction is created and submitted.</td>
<td><p>It is a best practice to return rejected payment requests to the submitting auditor using a separate workflow folder.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>Are rejected payment requests returned to the submitting user, or to a different user/group?</p></li>
<li><p>Should returned invoices be separated from recently received invoices in an auditor’s work folders?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>Closure<br />
</strong>(System)</td>
<td>This is a valid final state. BillTrak closes an invoice upon completion of the transaction. Since no action can be performed on a closed invoice, the client may configure a Re-Opened Invoice state, enabling users to re-enter an invoice into workflow to perform additional activity.</td>
<td>This is a required state.</td>
</tr>
<tr>
<td><strong>Re-Opened Invoices</strong> (Review)</td>
<td>During this review state users perform additional work on a closed invoice.</td>
<td><p>It is a best practice to identify a workflow state to receive invoices upon being re-opened, such as paid invoices in Closure or rejected invoices in Invalid Invoices.</p>
<p>It is a best practice to create a separate workflow state, such as Re-Opened Invoices; however, an invoice can be moved to any one of the other invoice review state, if the client wants to minimize the number of auditor work folders.</p>
<p><u>Considerations</u>:</p>
<ul>
<li><p>Under what circumstances would you expect to re-open a paid invoice?</p></li>
<li><p>Should re-opened invoices be moved to a separate work folder?</p></li>
</ul></td>
</tr>
</tbody>
</table>

The following table provides a detailed list of transaction workflow states included in the baseline workflow configuration.

<table>
<colgroup>
<col style="width: 18%" />
<col style="width: 40%" />
<col style="width: 41%" />
</colgroup>
<thead>
<tr>
<th>Workflow State</th>
<th>Purpose</th>
<th>Best Practices and Considerations</th>
</tr>
</thead>
<tbody>
<tr>
<td><strong>Initial<br />
</strong>(System)</td>
<td>During this transitory system state transactions enter the BillTrak transaction workflow.</td>
<td>This is a required state.</td>
</tr>
<tr>
<td><strong>Auto Coder<br />
</strong>(System)</td>
<td>During this system state the Auto Code executable attempts to assign account codes to each transaction by automatically initiating the account code compute function. If the system cannot account code based on established system rules, then the auditor will be required to review and update with codes in the Account Code (AC) Review state.</td>
<td><p>To reduce time spent manually account coding transactions, and to include all transactions in the Invoice and Account Code Details universe, it is best practice to use Auto Coder.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>Do you need to account code transactions with $0 payments?</p></li>
<li><p>Do you want all transactions included in the Invoice and Account Details universe?</p></li>
<li><p>When BillTrak is unable to completely account code the payment transaction, to whom should the transaction be assigned to review and continue processing manually?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>AC<br />
</strong>(Review)</td>
<td>During this state the auditors can update incompletely account-coded transactions. This state can also be configured to receive incorrectly account-coded transactions from one of the transaction approval states, eliminating the need for rejecting the transaction when only account code reassignment is required.</td>
<td><p>When Auto Coder is used, it is best practice to have a review state to review auto account coding. This reduces the need to reject the transaction due to incomplete account coding.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>Is the same person who audited the invoice responsible for account coding?</p></li>
</ul></td>
</tr>
<tr>
<td><p><strong>Supervisor Approval</strong> (Review)</p>
<p>and</p>
<p><strong>Manager Approval</strong> (Review)</p></td>
<td>During this review state supervisors or managers review transactions. When approved, the transaction transitions to the next state. When rejected, the transaction transitions to the Rejected Transactions state, where it can be viewed, but cannot be updated or re-submitted by the auditor. Transactions with incorrect account coding can be returned to the AC review state.</td>
<td><p>It is a best practice to establish a payment approval hierarchy to review all transactions.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>Are there any circumstances in which a payment would not require review and approval?</p></li>
<li><p>How many approval levels exist in your organization?</p></li>
<li><p>If more than one, does each level have to approve each transaction before the next level can approve it? Or, is the payment request assigned to the highest approval level based on payment amount?</p></li>
<li><p>What is the dollar amount, or other payment characteristics, associated with each approval level?</p></li>
<li><p>Are there any approval levels in which the approving authority would not have access to BillTrak, such as a Vice President? If so, what documentation is required to obtain approval?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>Rejected Transaction</strong> (System)</td>
<td>This is an invalid final state. Rejected transactions can be viewed, but cannot be updated or re-submitted.</td>
<td>This is a required state.</td>
</tr>
<tr>
<td><strong>A/P Exception</strong> (System)</td>
<td>During this review state a file containing rejected transactions is imported from the Accounts Payable (A/P) system. The transaction may require additional work, such as account coding corrections, or complete transaction rejection.</td>
<td><p>It is best practice to use A/P exception to review all A/P related rejections to allow either correction or complete transaction reject. It is best practice to have the Access Cost Manager review transactions rejected by the A/P system.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>Can the A/P system reprocess transactions that were submitted but were found with an error? Or, is a completely new transaction needed?</p></li>
<li><p>What is the key data that your A/P system uses to identify unique transactions?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>A/P Send</strong> (System)</td>
<td>During this system state approved transactions are exported to a file containing pertinent accounts payable information for each approved transaction, which is then sent to the A/P system.</td>
<td><p>It is best practice to use A/P Send only when the A/P system interface is being used. Otherwise, a review state could be used to manually process the payment information.</p>
<p><u>Consideration:</u></p>
<ul>
<li><p>Do you plan to implement an Accounts Payable interface?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>A/P Confirm</strong> (System)</td>
<td>During this system state a file confirming receipt of transaction information is imported from the A/P system.</td>
<td><p>It is best practice to use A/P Confirm only when using an A/P system interface.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>Can your A/P interface produce a confirmation?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>A/P Payment</strong> (System)</td>
<td>During this system state a file containing payment information for each transaction is received from the A/P system.</td>
<td><p>It is best practice to use A/P Payment only when the A/P system interface is being used.</p>
<p><u>Considerations:</u></p>
<ul>
<li><p>Can your A/P system provide a payment file in the BillTrak format or will this be handled manually?</p></li>
</ul></td>
</tr>
<tr>
<td><strong>Closure</strong> (System)</td>
<td>This is a valid final state. Upon entering this state, the associated invoice moves from Transaction Processing to Closure.</td>
<td>This is a required state.</td>
</tr>
</tbody>
</table>