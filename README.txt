MEMBER CSV CLEANER
User guide for Membership Services
Fund for the Public Interest Network

The Member CSV Cleaner prepares incoming member lists for the CRM. It formats
common fields, brings possible duplicates and uncertain values to your
attention, and saves a new CSV with the columns in your chosen template.
The Rules Reference after the save instructions explains what gets cleaned,
what needs review, and which records can be saved.

WHAT YOU NEED

- The Member CSV Cleaner Windows executable. Open it directly; you do not
  need Python.
- A source CSV containing your member records. The first row should contain
  the source column names.
- A template CSV containing only the destination column names. The template
  controls the exact names and order of the columns in the saved file.

Both files should be comma-separated CSVs saved as UTF-8. Use the supplied
CRM template for regular member imports. If Membership Services updates the
template, use Browse to select the replacement when you run the program.
You can also choose another template for lists that use the same cleanup rules.

1. CHOOSE YOUR FILES AND MATCH THE COLUMNS

Select Browse beside Source CSV and choose the incoming file. Use Browse
beside Header-only template to choose the template. Select Load columns.

Select Suggest column matches to fill in clear matches by column name.
Check the suggestions against the sample values. Choose a destination for
each remaining source column. For example, a source column called Given
Name belongs in First Name. Use Ignore this column for information that
does not belong in the output. Only one source column can fill each
destination. A template column without a source can be left unmapped.

If the source has a separate apartment or suite column, map the main address
to Street and choose Separate street unit for the apartment or suite column.
The program puts both in Street. If the unit is already part of the street
text and has no separate column, just map the street to Street.

2. SET THE PETITION GROUP AND PREPARE THE BATCH

If all records belong to one petition group, type the group's code in Batch
petition group. Select Prepare batch to apply it and run cleanup. This
replaces any petition values already supplied for those records. You can
leave the box empty to retain mapped petition values, including blanks.
The template needs a PROISSUB or PROISSSUB column for this option.

If you change the group after preparation, select Apply to all records.
Changing a group's value can reopen duplicate review, so it is easier to
enter the code before reviewing duplicates.

3. REVIEW POSSIBLE DUPLICATES

If the main window shows possible duplicate pairs, select Review duplicates.
The screen explains what matched. Compare Prepared values and Original CSV
values to see the cleaned and source information side by side. Record
numbers follow the order of data records in the source file.

Choose Keep both if both records belong in the output. Choose Keep record
N only to retain that record and omit the other; the program does not merge
their fields. Choose Exclude both and enter a reason if neither should be
saved. To change a choice, select it under Decisions for this batch and
click Undo selected decision. Resolve the remaining pairs to continue.

Confirmed duplicates are listed with their decision on this screen.
The Excluded records view in field review is for individual exclusions,
records omitted with Exclude both, and records without usable contact.

4. REVIEW AND CORRECT FIELDS

If records are waiting for review, open Review and correct records.
The Needs field review view lists included records still waiting for a
decision. Select a flagged field to see the reason and compare the original
mapped value, current value, and value prepared for the CSV. Switch to
All fields to inspect other fields. You can also open this screen to
browse records when no review is required.

- Edit selected field opens with the current value ready to edit. If
  cleanup left a supplied field blank, the editor shows the original
  text as a starting point. A field you deliberately cleared stays
  blank when reopened. The program cleans and checks your correction.
  If the edit changes a duplicate match, return to duplicate review.
- Accept prepared values accepts the values shown for the entire record,
  including any blanks or remaining flags. Check the prepared values
  before accepting. If you cannot confirm a signing date, leave it blank.
- Exclude record removes that record from the output and asks for a reason.
  In Excluded records, use Restore record to reverse an exclusion made
  during review. The record still needs usable contact information. If it
  was excluded for lack of usable contact, correcting a contact field can
  make it eligible again.

When the Field review complete panel appears, select Return to save.
Select Browse records if you want another look before saving.

5. SAVE THE CLEANED CSV

Select Save cleaned CSV and choose a folder and a new filename. The
confirmation shows the number of saved records and the file location.
Use Open containing folder to find the file for your usual CRM process.
The program does not upload anything to the CRM.

The source file, template, and existing output files are protected from
overwriting. Review choices apply to the current batch. Save the cleaned
file before closing or switching files if you want to keep the results.

RULES REFERENCE

These rules reflect the Membership Services review sheet and the later
clarifications used in the current program. Examples use fictional data.

Names and record eligibility

- A record needs at least one usable contact: a valid Email, a qualifying
  Primary Cell/Mobile Phone, or a complete address that qualifies as
  MAILABLE. One is enough. A record with none is excluded before duplicate
  review. The reason and original values are available for review, and a
  verified contact correction can make the record eligible again.
- First Name and Last Name are trimmed and repeated spaces are reduced
  to single spaces. Names entered as JORDAN or jordan become Jordan.
  This applies to each name part. Existing mixed case is kept: McDonald stays
  McDonald, while mcdonald becomes Mcdonald. Apostrophes and hyphens are
  preserved. Compound names stay in their original field: BRITTANY SUE
  becomes Brittany Sue, and nunez-lopez becomes Nunez-Lopez.
- Periods are removed from single-letter initials. J. Taylor becomes
  J Taylor, and Jordan T. becomes Jordan T. A usable first name with no
  last name can be kept with usable contact; Last Name stays blank and
  is not flagged solely for being blank.
- If both names are missing, only the last name is supplied, or the only
  name information consists of initials (such as J. T., J., or T),
  eligible records are prepared with First Name Anonymous and Last Name
  Donor. Any one qualifying contact method is enough for Anonymous Donor.
  The original name fields remain available in review.

Mobile phone and email

- Primary Cell/Mobile Phone is the phone field used for cleanup,
  eligibility, and duplicate matching. Home and work phone values do
  not count toward these checks or get copied into the mobile field.
- Phone cleanup removes spaces, parentheses, hyphens, and periods.
  It removes a leading US country code of 1 only when the number has
  eleven digits including that code. For example, 1 (202) 555-0147
  becomes 2025550147. The cleaned number must have exactly ten digits.
  Wrong lengths, unsupported country codes, extensions, and multiple
  numbers in one field need review.
- Email cleanup trims spaces at the beginning and end. It repairs a
  single comma before a supported ending (com, org, net, edu, gov, mil,
  or us) when the domain is otherwise one label, then checks the result.
  For example, jordan@example,com becomes jordan@example.com.
- A supported email is one plain address with one @ and a domain with
  a dot, such as jordan@example.com. Internal spaces, two addresses
  in one field, extra @ signs, or other unsupported formats need review.
  Check the source and enter one verified address. The program will not
  guess how to join broken pieces or which address to keep.
- A missing phone or email is allowed when another contact qualifies.
  Supplied phone or email values that fail the checks are flagged and
  left blank in the prepared CSV until corrected. Format checks cannot
  tell whether a number is active or a mailbox exists.

Address formatting and status

- Street and City cleanup removes periods and commas from ordinary
  address text, trims extra spaces, and uses conservative capitalization.
  Street suffixes and directions are abbreviated where their position
  supports it (for example, Street becomes St and East can become E).
  An ambiguous direction or unit in a street name needs review.
- A street address needs a supported house number, a street name, and a
  recognized suffix. A missing suffix always needs review. For example,
  125 Elm does not become 125 Elm St by assumption. Missing city, state,
  or ZIP information is not filled in from the other fields.
- A numbered PO box can qualify as Street when the other address checks
  pass. P.O. Box #00027 becomes PO Box 00027. A bare PO Box or an
  unsupported box number leaves Street blank for review; no box number
  is guessed.
- Unit information goes at the end of Street. For example, 125 Elm
  Street plus Apartment 4B becomes 125 Elm St Apt 4B. A bare 004B
  in a separate unit column becomes # 004B. Matching units are written
  once. Conflicting or unsupported unit information is flagged so you
  can confirm the complete Street value.
- A recognized state name or code is written as a two-letter postal
  code: Colorado becomes CO. City should contain just the city name.
  Zipcode must be five digits. Leading zeros are kept, and a valid
  ZIP+4 such as 02108-1234 becomes 02108. A value such as 2108 is
  flagged; the program does not assume a missing zero.
- Country stays blank if absent. Recognized US forms such as US, U.S.A.,
  United States, and United States of America become USA. A different
  supplied country is retained and an address with that country is
  marked BAD_ADDRESS.
- Address Contact Status is MAILABLE only when Street, City, State, and
  Zipcode are all present, pass the local checks, and have no unresolved
  address issues. Country must be blank or USA. Otherwise the status is
  BAD_ADDRESS. An entirely absent address does not need review by itself
  if another contact qualifies. If an address is partly supplied, missing
  or uncertain parts are flagged; available parts can stay in the output
  with BAD_ADDRESS after review. The program does not check that the
  street exists, the ZIP matches the city, or mail can be delivered.

Signing date

- DateSigned accepts supported US month/day/year dates with a two- or
  four-digit year and saves valid dates as MM/DD/YY. For example,
  2/9/2024 becomes 02/09/24. This is the current output format.
- In this version, two-digit years mean 2000 through 2099. Four-digit
  years must also fall in that range. The date must be a real calendar
  date and cannot be later than the day the batch was prepared.
- Missing, unclear, impossible, future, or unsupported dates are flagged
  and prepared as blank. The original value is shown in review. Enter a
  verified date if one is available, or accept the blank after review.
  The program does not swap month and day or supply a date. A date issue
  alone does not exclude a record with usable contact.

Duplicate and petition rules

- The program checks eligible records within the current file. A pair
  needs matching cleaned First Name and Last Name plus at least one
  matching usable contact: Email, Primary Cell/Mobile Phone, or a complete
  MAILABLE address. Comparisons ignore case and extra spaces. An address
  match compares Street including any unit, City, State, and Zipcode.
  Blank or unusable contact values do not count. Different first names
  at the same address do not match.
- Two first-name-only records may match if their cleaned first names
  match, both last names are blank, and they share a usable contact.
  A blank last name does not match a populated last name. Two Anonymous
  Donor records still need a matching usable contact; the placeholder
  name alone does not make them duplicates.
- Different nonblank petition codes keep the records separate, even if
  the names and contacts match. Petition comparisons ignore case and
  extra spaces. One or two blank petition values still allow a possible
  match if names and contact match. A blank petition alone is allowed
  and does not prevent saving.
- Even identical records are presented for review. The program does
  not automatically merge records or decide which record to keep.
  Confirmed duplicate exclusions leave the original file intact.
  Corrections or petition changes can reveal or reopen matches; review
  those pairs before saving.

Fixed values and other output columns

- Every saved record gets PhoneDisclaimeredYN = Y and
  Account Classification = INDIVIDUAL if those columns are in the
  template. The program calculates Address Contact Status from the
  prepared address rather than trusting an incoming status.
- The chosen template determines the exact output column names and
  order. Other mapped values, such as Prefix, Birth Date, or verification
  dates, are copied as supplied. Unmapped fields without a calculated
  value stay blank. The program does not add columns or invent values.

IF YOU GET STUCK

- Load columns reports an error: Check that both files are UTF-8 CSVs, the
  template has no data rows or repeated headings, and the source has the
  same number of columns in each data record as in its heading row.
- Prepare batch reports a mapping error: Give every source column a
  destination or choose Ignore this column. Make sure no destination is
  used twice, and map Street before using Separate street unit.
- Save cleaned CSV is unavailable: Read the next step under the buttons.
  Finish duplicate and field review, apply any pending petition change,
  and make sure at least one record is included.
- A ZIP or date looks different when opened in a spreadsheet: Spreadsheet
  software may display CSV values as numbers or dates. Open the CSV in a
  text editor to check the saved text before making any changes.

Use fictional data when practicing or reporting an issue. If you need help,
note which step you were on, the record number, and the exact message.

Developed by Wade Eckert for the Bellevue University Civic Engagement
Project, with assistance from OpenAI ChatGPT.
