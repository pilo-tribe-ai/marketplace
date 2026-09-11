# How to sign in

This file holds instructions. It never holds a value.

/ui-judge:setup writes this file. It asks you where each secret lives, and it
records only the place, never the secret.

## shopper

Where to get the details
  First, try this command:
    infisical secrets get SHOP_USER SHOP_PASS --plain
  If the command fails, read these environment variables:
    UIJUDGE_SHOPPER_USER
    UIJUDGE_SHOPPER_PASS
  If both fail, ask the person running the command, one time only. Hold the
  answer in memory. Never write it down.

How to sign in
  Look for a "Sign in" link near the top of the page.
  Put the user value in the email box.
  Put the pass value in the password box.
  Then submit the form.
  You are signed in when the page shows the shopper's name.

After signing in
  Save the browser session to .uijudge/auth/shopper.json.
  Use that session again until it stops working.

Never
  Never write these values into a verdict, a screenshot, a trace, a test, or
  the conversation.
  Name them only as <shopper user> and <shopper pass>.
  Never take a screenshot while a password box has the cursor in it.
