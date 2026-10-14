# Putting ForgeTrack on Google Play

ForgeTrack is a web app (PWA). Google Play accepts it wrapped as a **Trusted Web Activity (TWA)**:
a small Android app that opens your site full screen, with no browser bar. You don't need to
rewrite anything in Java or Kotlin.

Rules change often. Check each item against the current Play Console help pages when you get there.

---

## What the app already has (done in code)

| Play requirement | Where it is |
|---|---|
| Privacy policy at a public URL | `/privacy.html` |
| Way to delete the account inside the app | Me → Delete account |
| Web page explaining account deletion (needed for the Data safety form) | `/delete-account.html` |
| Clear consent before collecting health data | Tick box on sign-up and on first Google sign-in |
| Not aimed at children | 16+ age check on sign-up and in the setup questions |
| Health disclaimer, no medical claims | Terms page, plan screen, plan-ready screen |
| User can download their data | Me → Download my data |
| Digital Asset Links for the TWA | `/.well-known/assetlinks.json` (filled from `AndroidPackage` + `AndroidCertSha256`) |
| No ads, no tracking SDKs, no third-party analytics | Nothing to declare |

## What you must do (needs your accounts)

1. **Google Play developer account.** play.google.com/console costs a one-time 25 USD and needs ID verification.
   New *personal* accounts must run a **closed test with at least 12 testers for 14 days in a row** before
   you can publish to everyone. Start recruiting testers early (friends, gym mates).
2. **Support email.** Use one you're happy to show publicly. Set it as `ContactEmail` when deploying. It
   appears on the privacy, terms and deletion pages and in the Play listing.
3. **Google sign-in** (optional but recommended):
   - console.cloud.google.com → new project "ForgeTrack" → *Google Auth Platform* → set up the OAuth consent
     screen (app name, support email, privacy policy URL, app logo).
   - *Clients* → *Create client* → **Web application**. Under *Authorised JavaScript origins* add your app URL
     (the AWS AppUrl without the trailing slash) and `http://localhost:8000` for testing.
   - Copy the **Client ID** and deploy with `GoogleClientId=<that id>`.
4. **Build the Android app** with PWABuilder (pwabuilder.com → enter your app URL → *Package for stores* →
   Android). It generates the signed app bundle (.aab) and an `assetlinks.json`. Copy the package name and
   the SHA-256 fingerprint into `AndroidPackage` / `AndroidCertSha256` and deploy again.
   After uploading to Play, also add the **Play App Signing** SHA-256 (Play Console → *Test and release* →
   *App integrity*), separated by a comma.
5. **Store listing.** Category *Health & Fitness*; short and full description (no "guaranteed results",
   no medical claims); 512×512 icon; 1024×500 feature graphic; at least 2 phone screenshots.
6. **App content forms** in Play Console:
   - *Privacy policy*: `<AppUrl>/privacy.html`
   - *Data safety*: see the table below.
   - *Health apps declaration*: a fitness/nutrition tracker, **not** a medical device.
   - *Target audience*: 16 and over (not designed for children).
   - *Content rating*: fill in the IARC questionnaire (no violence, no user-to-user chat, no gambling).
   - *Ads*: No ads.
   - *Account deletion*: in-app path + `<AppUrl>/delete-account.html`.
7. **A stable web address.** The AWS Function URL works, but it changes if the stack is ever deleted and
   recreated, and the Android app is tied to that address. Before publishing, consider a custom domain
   (e.g. `forgetrack.app`) in front of it.
8. **Trademark.** No app called exactly "ForgeTrack" was found (Oct 2026), but several "Forge…" fitness apps exist.
   Search tmsearch.uspto.gov and WIPO Global Brand Database before you publish.

## Data safety form: suggested answers

| Data type (Play's names) | Collected | Shared | Purpose | Optional? |
|---|---|---|---|---|
| Personal info: Name | Yes | No | Account management | Required |
| Personal info: Email address | Yes | No | Account management | Required |
| Health and fitness: Health info (weight, injuries, body measurements) | Yes | No | App functionality, personalisation | Required for a plan |
| Health and fitness: Fitness info (workouts, steps, sleep) | Yes | No | App functionality, analytics (improving plans) | Optional (user logs it) |
| Other: food preferences, budget | Yes | No | App functionality, personalisation | Required for a plan |

- Data is **encrypted in transit** (HTTPS): Yes.
- Users can **request deletion**: Yes (in app, and by the web page).
- Hosting on AWS counts as a *service provider*, not "sharing".

## Before you press Publish

- [ ] Deployed with `SignupCode` empty, `ContactEmail` set, `AdminEmails` = your email
- [ ] Tested sign-up, Google sign-in, setup questions, daily tasks, deleting an account on a real Android phone
- [ ] Privacy policy URL opens without logging in
- [ ] Closed test finished (12+ testers, 14+ days)
- [ ] AWS bill alarm email confirmed
