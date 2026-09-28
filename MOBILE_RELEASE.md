# Releasing the iOS and Android apps from Windows

This is the whole path from a working website to Pedagogue in the App Store and
Google Play, done from a Windows PC. You never need a Mac: Codemagic builds and
signs the iOS app on its own Macs and uploads it to TestFlight.

Plan on about three weeks end to end. Most of that is waiting: Apple takes a day
or two to approve a developer account, and Google requires a 14-day closed test
before a new personal account can publish.

| Step | Where | Time |
|---|---|---|
| 1. Deploy the backend and website | Render (see `DEPLOY.md`) | 1 hour |
| 2. Create the demo account | Render shell | 5 minutes |
| 3. Apple Developer Program | developer.apple.com | 1 to 2 days to approve |
| 4. Google Play Console | play.google.com/console | 1 to 3 days to verify |
| 5. Signing keys and Codemagic | codemagic.io | 1 hour |
| 6. First builds and TestFlight | Codemagic, App Store Connect | 1 hour |
| 7. Google Play closed test | Play Console | 14 days minimum |
| 8. Privacy and data forms | both consoles | 1 hour |
| 9. Store listings and screenshots | both consoles | 2 hours |
| 10. Submit for review | both consoles | 1 to 7 days |

Costs: Apple Developer Program $99 a year, Google Play $25 once, Codemagic free
tier (500 build minutes a month on Apple silicon Macs, enough for about 25 iOS
builds), plus the Render services in `DEPLOY.md`.

Everything below uses these values. Change them in one place if you change them:

| Value | Used for |
|---|---|
| `com.pedagogue.app` | iOS bundle ID and Android package name |
| `Pedagogue` | App name on the home screen |
| `https://pedagogue.app` | Your website (replace with your domain) |
| `https://api.pedagogue.app` | Your backend (replace with your API domain) |

---

## 1. Deploy the backend and website

Follow `DEPLOY.md` to the end, including custom domains. Before going further,
check both of these open in a browser:

- `https://pedagogue.app/privacy`, the privacy policy, which both stores link to
- `https://api.pedagogue.app/health`, which should say `"database": true`

Set `VITE_CONTACT_EMAIL` on the `pedagogue-web` service to the support address
you want on the privacy policy (for example `support@pedagogue.app`) and
redeploy. Both stores require a way to contact you.

## 2. Create the demo account

Both review teams need an account that already has data in it.

1. In the Render dashboard, open `pedagogue-api` and choose **Shell**.
2. Run, with a password of your own:

   ```bash
   python -m app.demo --email review@pedagogue.app --password 'Choose-A-Long-Password-1'
   ```

   It prints `created demo account review@pedagogue.app`. The account is fully
   set up: a finished onboarding, six pieces at different stages, practice
   notes, rated techniques, XP and gold. Running it again only resets the
   password, so do that if a reviewer changes it.
3. Sign in on the website with it once to check it works.

The email does not need to receive mail: the app never sends email.

## 3. Apple Developer Program

1. On your iPhone (or at <https://appleid.apple.com>), make sure your Apple
   Account has two-factor authentication turned on.
2. Go to <https://developer.apple.com/programs/enroll/> and choose
   **Start your enrollment**. Sign in with that Apple Account.
3. Enrol as an **Individual / Sole Proprietor**. Your legal name becomes the
   seller name shown on the App Store. (Enrolling as an organisation needs a
   D-U-N-S number and takes longer.)
4. Pay the $99 fee. Approval usually takes 24 to 48 hours and arrives by email.
   If the web flow stalls, install the **Apple Developer** app on an iPhone and
   enrol from there.

### 3a. Register the bundle ID

1. Go to <https://developer.apple.com/account/resources/identifiers/list>.
2. Choose **+**, then **App IDs**, then **App**.
3. Description `Pedagogue`, Bundle ID **Explicit** `com.pedagogue.app`.
4. Capabilities: leave everything unticked. The daily reminder is a local
   notification and needs no Push Notifications capability.
5. **Continue**, then **Register**.

### 3b. Create the app in App Store Connect

1. Go to <https://appstoreconnect.apple.com>, then **Apps**, then **+**, then **New App**.
2. Platforms **iOS**. Name `Pedagogue: Piano Practice` (it must be unique on
   the store; see `STORE_LISTING.md` for a fallback). Primary language
   **English (U.K.)**. Bundle ID `com.pedagogue.app`. SKU `pedagogue-ios`.
   User access **Full Access**.
3. Open the new app, go to **App Information**, and copy the **Apple ID**
   number (for example `6740000000`). This becomes `APP_STORE_APPLE_ID`.

### 3c. Create an App Store Connect API key

Codemagic uses this key to create certificates and upload builds.

1. In App Store Connect go to **Users and Access**, then **Integrations**, then
   **App Store Connect API**, then **Team Keys**. Request access if asked.
2. **Generate API Key**. Name `Codemagic`, access **App Manager**.
3. Download the `.p8` file. Apple lets you download it only once, so keep it
   somewhere safe.
4. Copy the **Issuer ID** (at the top of the page) and the key's **Key ID**.

### 3d. Create the certificate private key

Codemagic creates the iOS distribution certificate for you but needs a private
key to create it with. In **Git Bash** (installed with Git for Windows):

```bash
ssh-keygen -t rsa -b 2048 -m PEM -f ~/pedagogue_ios_distribution_key -q -N ""
cat ~/pedagogue_ios_distribution_key
```

Copy everything it prints, from `-----BEGIN RSA PRIVATE KEY-----` to
`-----END RSA PRIVATE KEY-----`. This becomes `CERTIFICATE_PRIVATE_KEY`. Keep
the file: every later build must use the same key.

## 4. Google Play Console

1. Go to <https://play.google.com/console/signup> with the Google account you
   want to own the app.
2. Choose **Yourself** (a personal account). An organisation account needs a
   D-U-N-S number but skips the 14-day closed test in step 7.
3. Pay the $25 fee and complete identity verification: your legal name,
   address and a photo of government ID. Google also asks you to confirm a
   phone number and, for new personal accounts, to prove you have an Android
   phone by installing the **Google Play Console** app on it and signing in.
   Verification takes one to three days.
4. When verified, choose **Create app**:
   - App name `Pedagogue: Piano Practice`
   - Default language **English (United Kingdom)**
   - **App**, **Free**
   - Tick both declarations, then **Create app**.

### 4a. Create the upload key

Google re-signs the app with its own key (Play App Signing). You sign uploads
with an upload key you create now. In PowerShell:

```powershell
cd $HOME
keytool -genkeypair -v -keystore pedagogue-upload.jks -alias upload -keyalg RSA -keysize 2048 -validity 10000
```

`keytool` comes with Java. If PowerShell can't find it, run it with its full
path, for example `& "C:\Program Files\Java\jre1.8.0_461\bin\keytool.exe" ...`,
or install the free Temurin JDK 21 from <https://adoptium.net>.

Choose a keystore password and answer the name questions (only the first one
matters). When asked for the key password, press Enter to reuse the keystore
password. Then turn the keystore into text for Codemagic:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$HOME\pedagogue-upload.jks")) | Set-Clipboard
```

The Base64 text is now on your clipboard for `ANDROID_KEYSTORE_BASE64`.
Back up `pedagogue-upload.jks` and its password somewhere safe (a password
manager). If you lose them you have to ask Google to reset the upload key.

### 4b. Service account for automatic uploads

This lets Codemagic send new builds to the closed test without you uploading
them by hand. It only works after the first manual upload in step 6b.

1. Go to <https://console.cloud.google.com>, create a project called
   `pedagogue-play`.
2. **APIs & Services > Library**, search **Google Play Android Developer API**,
   **Enable**.
3. **IAM & Admin > Service Accounts > Create service account**, name
   `codemagic`. Skip the optional role steps.
4. Open the new service account, **Keys > Add key > Create new key > JSON**.
   A `.json` file downloads. Its whole contents become
   `GCLOUD_SERVICE_ACCOUNT_CREDENTIALS`.
5. In the Play Console, **Users and permissions > Invite new users**. Paste the
   service account's email (ends in `iam.gserviceaccount.com`). Under **App
   permissions** add Pedagogue and tick **Release apps to testing tracks** and
   **Release to production, exclude devices, and use Play App Signing**.
   **Invite user**.

## 5. Codemagic

1. Sign up at <https://codemagic.io/signup> with GitHub and allow access to
   `creamfruit/pedagogue`.
2. **Add application**, pick the repository, project type **Capacitor** (or
   "Other"), and when asked choose **codemagic.yaml**. Codemagic reads the
   file from the branch you build.
3. Open the app, then **Environment variables**, and add these. Tick **Secret**
   for every row marked secret. The group names must match exactly.

| Group | Variable | Value | Secret |
|---|---|---|---|
| `pedagogue_web` | `VITE_API_URL` | `https://api.pedagogue.app` | no |
| `pedagogue_web` | `VITE_WEBSITE_URL` | `https://pedagogue.app` | no |
| `pedagogue_web` | `VITE_CONTACT_EMAIL` | your support address | no |
| `app_store_credentials` | `APP_STORE_CONNECT_ISSUER_ID` | Issuer ID from 3c | yes |
| `app_store_credentials` | `APP_STORE_CONNECT_KEY_IDENTIFIER` | Key ID from 3c | yes |
| `app_store_credentials` | `APP_STORE_CONNECT_PRIVATE_KEY` | the whole `.p8` file, including the BEGIN and END lines | yes |
| `app_store_credentials` | `CERTIFICATE_PRIVATE_KEY` | the key from 3d | yes |
| `app_store_credentials` | `APP_STORE_APPLE_ID` | the Apple ID number from 3b | no |
| `android_signing` | `ANDROID_KEYSTORE_BASE64` | the Base64 text from 4a | yes |
| `android_signing` | `ANDROID_KEYSTORE_PASSWORD` | keystore password | yes |
| `android_signing` | `ANDROID_KEY_ALIAS` | `upload` | yes |
| `android_signing` | `ANDROID_KEY_PASSWORD` | key password (the same as the keystore password if you pressed Enter) | yes |
| `google_play` | `GCLOUD_SERVICE_ACCOUNT_CREDENTIALS` | the whole JSON file from 4b | yes |

To open a `.p8` or `.json` file for copying, right-click it and choose
**Open with > Notepad**.

`codemagic.yaml` defines three workflows:

| Workflow | What it does | Needs groups |
|---|---|---|
| `ios-testflight` | Builds the web app, signs the iOS app, uploads it to TestFlight | `pedagogue_web`, `app_store_credentials` |
| `android-bundle` | Builds a signed `.aab` you download | `pedagogue_web`, `android_signing` |
| `android-play` | The same, then uploads it to the Play closed testing track as a draft | all three Android groups |

The version shown in the stores is `APP_VERSION` near the top of each workflow
in `codemagic.yaml` (`1.0.0` now). Raise it for each release you send for
review. Build numbers go up by themselves.

## 6. First builds

### 6a. iOS to TestFlight

1. In Codemagic choose **Start new build**, branch `mobile-apps` (or `main`
   once merged), workflow **iOS to TestFlight**.
2. After about 15 minutes the build finishes and uploads. Apple then processes
   it for 10 to 30 minutes; you get an email when it is ready.
3. In App Store Connect, open **TestFlight**. Export compliance is already
   answered by the app (it only uses standard HTTPS).
4. **Internal Testing > +** to create a group, add yourself (and up to 100
   people with App Store Connect access). Install **TestFlight** from the App
   Store on your iPhone and accept the invitation.
5. For outside testers, create an **External Testing** group. The first
   external build goes through a short Beta App Review (about a day), which
   uses the same review notes as in step 10.

If the build fails at "Fetch signing files", check the four
`app_store_credentials` values, especially that the `.p8` includes its BEGIN
and END lines.

### 6b. Android: the first upload is manual

Google only accepts API uploads for an app that already has one release.

1. In Codemagic run the **Android App Bundle (download only)** workflow.
2. When it finishes, download `app-release.aab` from the build's artifacts.
3. In the Play Console open Pedagogue, **Test and release > Testing > Closed
   testing**. Use the default track (**Closed testing - Alpha**) and choose
   **Create new release**.
4. When asked about app signing, keep **Use Google-generated key**. Upload
   `app-release.aab`, release name `1.0.0`, release notes `First test build.`
   **Next**, then **Save**. Leave it unsent until step 7 is set up.

From now on, run **Android to Google Play closed testing** instead. It creates
a draft release on the same track, which you open in the Play Console and roll
out.

## 7. The Google Play closed test (12 testers, 14 days)

New personal developer accounts must run a closed test with **at least 12
testers who stay opted in for at least 14 days in a row** before the
**Production** track unlocks. The clock only counts days when at least 12
testers are opted in, so recruit a few spares (15 to 20 is safer).

1. Collect testers' Google account emails (the address they use for Play on
   their Android phone). Friends, family, students and piano forums all work.
2. In the Play Console, **Closed testing > Alpha > Testers**. Choose **Create
   email list**, name it `Pedagogue testers`, and paste the emails
   (comma separated), or use a Google Group's address instead of a list.
3. Enter a feedback email or URL, **Save**.
4. Copy the **opt-in link** (Join on Android). Send it to every tester with
   these instructions:
   - open the link on the Android phone, signed into the same Google account
   - tap **Become a tester**, then **Download it on Google Play**
   - install and open Pedagogue, create an account or sign in with the demo
     account, and use it a few times over the two weeks
   - stay opted in: don't leave the test or uninstall until you say so
5. Send the release: open the draft from 6b (or from the `android-play`
   workflow), **Review release**, **Start rollout to Closed testing**. The
   first closed release goes through a review of a few hours to a few days.
6. Before the test ends, fill in steps 8 and 9 so they are ready.
7. After 14 days, the Dashboard shows **Apply for production**. Google asks
   about the test: how you recruited testers, what feedback you got, and what
   you changed. Answer honestly and specifically. Approval takes up to 7 days.

Tips: pushing updates during the test is fine and shows engagement. Ask
testers to leave feedback through the Play Store's private feedback option.

## 8. Privacy and data forms

These answers describe what the code actually stores (see the privacy policy at
`/privacy`, written from the same list). If you turn on
`VITE_AUDIO_FEATURES=on` later, add the audio rows marked below before that
release.

### 8a. App Store: App Privacy

App Store Connect > your app > **App Privacy**. Privacy Policy URL:
`https://pedagogue.app/privacy`. Choose **Get Started**, then **Yes, we collect
data from this app**, and tick these data types:

| Category | Data type | Why it's collected |
|---|---|---|
| Contact Info | **Email Address** | the sign-in email |
| Contact Info | **Name** | the optional display name |
| Identifiers | **User ID** | the account ID |
| User Content | **Other User Content** | repertoire, practice notes, practice sessions and plans, uploaded scores (PDF, MusicXML, MIDI) |
| Other Data | **Other Data Types** | years playing, self-assessed level, hand span, technique ratings |

For **each** type answer:

- Used for: **App Functionality** only (not analytics, not advertising, not
  product personalisation beyond the app's own features)
- Linked to the user's identity: **Yes**
- Used for tracking: **No**

Do not tick Location, Contacts, Health and Fitness, Financial Info,
Browsing History, Search History, Purchases, Diagnostics, Usage Data or any
advertising data: the app collects none of them. (When audio is turned on,
add **User Content > Audio Data**, App Functionality, linked, not tracking.)

### 8b. Google Play: Data safety

Play Console > **Policy and programs > App content > Data safety**.

Overview questions:

| Question | Answer |
|---|---|
| Does your app collect or share any of the required user data types? | **Yes** |
| Is all of the user data collected by your app encrypted in transit? | **Yes** |
| Which of the following methods of account creation does your app support? | **Username and password** |
| Delete account URL | `https://pedagogue.app/privacy#delete-account` |
| Do you provide a way for users to request that some or all of their data is deleted, without deleting the account? | **No** (users can delete individual pieces and notes in the app; answer Yes if you want to list that) |

Data types (every one: **Collected** yes, **Shared** no, **Processed
ephemerally** no, **Required**, except Name which is **Optional**; purpose
**App functionality**, plus **Account management** for email and user ID):

| Category | Data type |
|---|---|
| Personal info | **Name**, **Email address**, **User IDs** |
| App activity | **Other user-generated content** (practice notes, repertoire), **Other actions** (practice sessions and minutes logged) |
| Files and docs | **Files and docs** (uploaded scores) |

"Shared" means sent to a third party for their own use. Hosting, storage and
the AI coach notes provider process data only on Pedagogue's behalf, which
Google counts as not shared. (When audio is turned on, add **Audio > Voice or
sound recordings**, collected, not shared, optional, app functionality.)

### 8c. Google Play: the other App content forms

| Form | Answer |
|---|---|
| Privacy policy | `https://pedagogue.app/privacy` |
| Ads | **No, my app does not contain ads** |
| App access | **All or some functionality is restricted**. Add instructions: name `Demo account`, username `review@pedagogue.app`, password (from step 2), "Sign in on the first screen." |
| Content rating | Start the questionnaire, category **Reference, News, or Educational**, answer No to violence, sexuality, language, drugs and gambling. For "Can users interact or exchange content?" answer **Yes**: friends see each other's constellations and display names appear on opt-in leaderboards. There is no chat. The expected rating is Everyone / PEGI 3. |
| Target audience | **13 to 15, 16 to 17, 18 and over**. Not designed for children. |
| News app | **No** |
| Health apps | **No** |
| Financial features | **None** |
| Government apps | **No** |
| Advertising ID | **No**, the app does not use an advertising ID |

## 9. Store listings and screenshots

Copy the text from `STORE_LISTING.md` into:

- App Store Connect > the app > **1.0 Prepare for Submission** (description,
  keywords, promotional text, support URL `https://pedagogue.app/privacy`,
  marketing URL `https://pedagogue.app`) and **App Information** (subtitle,
  category Music, secondary Education, age rating questionnaire: answer
  none to everything; there is no unrestricted web access and no messaging).
- Play Console > **Grow users > Store presence > Main store listing** (short
  and full description, app icon 512 x 512, feature graphic, screenshots).

App icon files: App Store Connect takes the icon from the build. For Play,
export a 512 x 512 PNG: open `frontend/ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png`
(1024 x 1024) in Paint, **Resize** to 50%, and save as a new PNG.

`STORE_LISTING.md` lists the six screenshots to capture and how to capture
them on Windows.

## 10. Submit for review

### 10a. App Review notes (App Store)

In **1.0 Prepare for Submission > App Review Information**:

- **Sign-in required**: ticked. Username `review@pedagogue.app`, password from
  step 2.
- **Contact information**: your name, phone and email.
- **Notes** (paste and adjust):

```
Pedagogue is a practice companion for pianists. The demo account above already has a repertoire, practice notes and progress, so every screen has content.

Where to look:
- Today: the next piece to practise, streak and pieces that need attention.
- Repertoire > Fur Elise: the piece page with its history, hardest passages by bar number and practice cues. "Share" shares the piece; "Add notes or a score" accepts practice notes and PDF, MusicXML or MIDI scores from Files.
- Constellation: the repertoire drawn as stars. Tap a star or a line; "share" shares the sky as an image.
- Practice: start a session and log minutes; sight-reading and polyrhythm exercises are generated in the app.
- Settings > Practice reminders: an optional daily local notification. It is off by default and notification permission is requested only when it is switched on.
- Settings > Account > Delete my account: permanently deletes the account and all its data after typing DELETE and the password. Please use a new account of your own if you want to try this, so the demo account stays available.

Native features: offline use (turn on Airplane Mode: the repertoire and piece pages still open, and notes written offline are sent when the connection returns), local notifications, haptic feedback on streaks and scores, the share sheet and the Files picker.

Recording uploads and live listening are shown as "Coming soon" and are not part of this version. There are no in-app purchases, subscriptions, ads or external payment links. XP and gold are earned only by practising and cannot be bought.

Privacy policy: https://pedagogue.app/privacy
```

Then **Add for Review** and **Submit to App Review**. Most reviews finish
within 48 hours. If the reviewer asks a question, reply in the Resolution
Center rather than resubmitting.

### 10b. Google Play production

After Google approves production access (step 7):

1. **Test and release > Production > Create new release**.
2. **Add from library** and pick the build that ran in the closed test, or
   run the `android-play` workflow and promote its release.
3. Release notes `First release.`, **Review release**, **Start rollout to
   Production**. The first production review takes a few hours to a few days.

## Releasing an update later

1. Merge your changes, deploy the website and backend as usual.
2. Raise `APP_VERSION` in `codemagic.yaml` (for example `1.0.1`) and push.
3. Run **iOS to TestFlight** and **Android to Google Play closed testing**.
4. iOS: in App Store Connect create version 1.0.1, pick the new build, submit.
   Android: promote the new closed-testing release to Production.

Only changes to the web code (`frontend/src`) need a new app build. Backend
changes reach the apps as soon as the backend deploys.

## When something goes wrong

| Symptom | Likely cause |
|---|---|
| The app shows "you appear to be offline" everywhere | `VITE_API_URL` in the `pedagogue_web` group is wrong or has a trailing `/api/v1`, or the API is down. Open `/health` in a browser. |
| Sign-in works on the website but not in the app | The API is rejecting the app's origin. Check `ALLOW_CAPACITOR_ORIGINS` is not `false` on `pedagogue-api`. |
| iOS build fails at signing | An `app_store_credentials` value is missing or the `.p8` lost a line. Delete the certificate in Certificates, Identifiers & Profiles if you changed `CERTIFICATE_PRIVATE_KEY`. |
| Android upload says the version code was already used | Run `android-play` (it asks Google for the latest code) instead of `android-bundle`. |
| Play rejects the upload's signature | The `.aab` was signed with a different upload key than the first upload. Use the same `pedagogue-upload.jks`. |
