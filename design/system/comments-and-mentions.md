# Comments and mentions: the panel

Serves COL-01 and HOM-05's comments and mentions (chunk 10). Written from
`docs/plans/briefs/CHUNK10_TASKS.md` (`c10-collab-design-b`, rulings 3, 9 and
10, and the defaults), `backend/apps/collab/app.md` (COL-S1, COL-S5, COL-S12)
and `design/screens/tenant-my-work.html` §6. The prototype has no comments
panel; this card fixes one panel for every place it appears. Values follow
`foundations.md`; nothing here adds a pill slot or a tone.

## Where it sits

| Surface | Subject | Placement |
|---|---|---|
| The change page (`tenant-change.html`) | the bank's case on that change (`change_case`) | a card below the case panels, headed "Comments" |
| The obligation page (`tenant-obligation.html`) | the obligation (`obligation`); the comments are the bank's own, in its tenant zone | a card below the register panels, headed "Comments" |
| My work (`tenant-my-work.html` §6) | none: a person's own comments and mentions across records | "Comments and mentions", tabs Mentions and My comments, below the four sections |

On a record page the panel reads `GET /comments?subjectType&subjectId` and
writes `POST /comments`, `PATCH` and `DELETE /comments/{commentId}`. On My work
it reads `GET /me/comments?about=mentioned|written`, each row the record's
title as a link and "{name} mentioned you" or the time, newest first; a kind
the reader cannot open is named in one line ("Cases are not shown here, because
your role cannot open them"), as the My work card draws it. My work has no
composer of its own: a comment is always written on its record, so the My work
row links there.

The panel shows only where the reader can read the subject: `GET /comments`
answers 404 otherwise, and the page around it is then the shared Not found.

## The list

- **Oldest first**, so a thread reads as a conversation, 20 a page; "Show
  more" at the foot loads the next page (newer comments). The count sits after
  the heading as a quiet muted number.
- **A comment:** the author's name at 500, then the time in `meta` in the
  tenant's timezone ("Today 14:20", "Yesterday 09:02", then the date), then
  "Edited" in `meta` when `editedAt` is set, joined by a middle dot. The body
  below in `body`, line breaks kept, links not rendered as links, no markdown.
  A mention in the body reads as the person's name at 500 with no "@" and no
  pill.
- **The author's own comment** carries "Edit" and "Delete" as ghost buttons,
  small (32 px), on the right of the name line; below 768 px they move under
  the body on the right. They come from `canEdit` and `canDelete` on each
  comment, never from comparing ids in the client, and never from a role:
  nobody may edit or delete another person's comment. `canEdit` turns false
  when the edit window closes (`COMMENT_EDIT_MINUTES`, 15 by default); Delete
  stays.
- **Editing** turns the body into the composer's textarea with its text, and
  "Cancel" and "Save" (primary, right). Saving replaces the text in place and
  adds "Edited". The replaced text is kept by the server and no screen shows it.
- **Deleting** asks once, inline: "Delete this comment?" with "Cancel" and
  "Delete" (danger, right). A deleted comment keeps its place, author and time
  and shows, in muted italic `body`, "Comment deleted". No body, no Edit, no
  Delete.
- **Empty:** "No comments yet" in muted `body`, with the composer below. No
  illustration, no dashed box: the composer is the next action.
- **Loading:** three skeleton rows of 48 px in the list's shape, `aria-busy`.
- **Error:** "Could not load the comments. Check your connection and try
  again." with "Try again", in place of the list; the composer stays hidden
  until the list loads, so nobody replies blind.

## The composer

- A label "Add a comment", a textarea (76 px minimum, grows with its text),
  and under it the hint, verbatim and identical on every surface:

  > Everyone in your organisation can read comments.

  Quoted from `design/screens/tenant-my-work.html` §6 (D-22, D-60, ADR 0028).
  There are no private notes and no per-person visibility, so no control
  suggests either.
- "Comment" (primary, small, right) is disabled while the text is empty or
  sending. On success the text clears and the new comment appears at the end
  of the list; focus returns to the textarea.
- **Mentions.** Typing "@" opens a list under the caret of people from
  `GET /reference/people`, filtered by the letters typed after it: name at 500,
  role and team in `meta`, arrow keys and Enter to choose, Escape to close. The
  list is a combobox (`aria-expanded`, `aria-activedescendant`); on a phone it
  opens above the keyboard at full width. A chosen person shows as their name
  in the text at 500 and is sent as a user id beside the body, never parsed
  back out of the text. No match reads "No one in your organisation matches
  '{letters}'".
- **A mention that reached nobody.** A mention notifies only someone who can
  read the record. When the answer to `POST /comments` names mentioned people
  who were not notified, the author sees one muted line under their new
  comment: "Not notified: Johan Berg." By name, never why: the reason is the
  other person's permissions. Nobody else sees the line, and it is not shown
  again after a reload.
- **Refusals** render under the textarea in `meta` in the negative colour, from
  the problem's `code`: text too long ("Keep it under {limit} characters", the
  limit from the API), an empty body, a lost permission ("You do not have
  permission to do this. Needs comments write"), a closed edit window on Save
  ("This comment can no longer be edited"). A network failure keeps the text in
  the textarea: "Could not post. Check your connection and try again."
- **No `comments.write`:** the composer is replaced by one muted line, "You can
  read comments here but not add them." Every system role holds it today, so
  this is a custom role's state.

## Widths

At 375 px the panel is the page's width inside the 16 px gutter; name, time
and "Edited" wrap onto two lines before the buttons move; Edit and Delete sit
under the body on the right, "Comment" stays on the right under the hint, and
the mention list is full width.

## What never appears

- Comment text in a notification title, an email, the URL, a toast or the
  document title. A notification about a mention carries the record's title and
  "{name} mentioned you" (`design/screens/tenant-notifications.html`).
- Reactions, threads, attachments, follow: none is built (CHUNK10_TASKS.md,
  cut list).
- A pill. Author, time, "Edited" and "Comment deleted" are text, so the panel
  adds no slot and no tone to `pills-and-labels.md`.

## Strings (catalog keys, `collab` namespace)

"Comments", "Comments and mentions", "Mentions", "My comments", "Add a
comment", "Everyone in your organisation can read comments.", "Comment",
"Edit", "Delete", "Delete this comment?", "Cancel", "Save", "Edited",
"Comment deleted", "No comments yet", "Show more", "Not notified: {names}.",
"No one in your organisation matches '{letters}'", "Could not load the
comments. Check your connection and try again.", "Try again", "Could not post.
Check your connection and try again.", "This comment can no longer be edited",
"You can read comments here but not add them.", "{name} mentioned you". Each
in en and sv; none survives as a string literal in JSX.
