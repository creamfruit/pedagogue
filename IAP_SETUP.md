# Setting up in-app purchases (RevenueCat, App Store, Google Play)

Pedagogue Pro is sold in the iOS and Android apps as a store subscription, with
RevenueCat sitting between the apps, the stores and the backend. This guide is
the whole setup, written for a Windows PC. You never need a Mac: the iOS build
and signing run on Codemagic (see `MOBILE_RELEASE.md`), and the only iOS device
you need is an iPhone to test on.

The website keeps selling through Stripe (`DEPLOY.md`, "Billing with Stripe
(Pro)"). Someone who subscribes anywhere is Pro everywhere: the backend keeps one
subscription row per account, whichever platform wrote it.

Store consoles rename and move things now and then. The names below are the
ones at the time of writing; if a button has moved, the quoted words are what to
search for.

## How it fits together

```
iPhone / Android app  --buys-->  App Store / Google Play
        |                               |
        | logIn(Pedagogue user id)      | receipts
        v                               v
              RevenueCat  --webhook-->  Pedagogue API
                                        /api/v1/billing/revenuecat/webhook
                                        writes the subscriptions row
```

- The app asks RevenueCat for the **offering** (the two plans) and shows the
  store's own price, in the customer's currency, plus the 7-day trial where the
  store offers one.
- The app logs RevenueCat in as the Pedagogue **user id** (a UUID) as soon as
  someone is signed in, and logs out when they sign out. That is how a store
  customer is linked to a Pedagogue account. Purchases are only possible when
  signed in.
- After the store sale, RevenueCat calls the webhook. The backend checks the
  shared secret, finds the user from the app user id, and sets or clears Pro. The
  app waits up to about 15 seconds for that and then welcomes the new member.

## What you will create

Use these identifiers exactly. The backend reads the plan length from the product
identifier (a name containing `month` is monthly, one containing `year` or
`annual` is yearly), and the apps match the two plans by RevenueCat package type.

| Thing | Value |
|---|---|
| Bundle ID (iOS) and package name (Android) | `com.pedagogue.app` |
| Monthly product, App Store | `pedagogue_pro_monthly` (1 month) |
| Yearly product, App Store | `pedagogue_pro_yearly` (1 year) |
| Subscription group, App Store | `Pedagogue Pro` |
| Monthly subscription, Google Play | subscription ID `pedagogue_pro_monthly`, base plan ID `monthly` |
| Yearly subscription, Google Play | subscription ID `pedagogue_pro_yearly`, base plan ID `yearly` |
| Free trial | 7 days, new subscribers only, on both plans on both stores |
| RevenueCat project | `Pedagogue` |
| RevenueCat entitlement | `pro` (both products attached) |
| RevenueCat offering | `default`, set as **Current** |
| Packages in the offering | **Monthly** (`$rc_monthly`) and **Annual** (`$rc_annual`) |
| Webhook address | `https://<your api address>/api/v1/billing/revenuecat/webhook` |

On Google Play, RevenueCat names a product `subscription ID:base plan ID`, so you
will see `pedagogue_pro_monthly:monthly` and `pedagogue_pro_yearly:yearly` in
RevenueCat. That is expected.

Keep the prices the same on both stores and on the website (for example $9.99 a
month and $79.99 a year) so people on different platforms see the same plans.

## Before you start

You need:

1. The backend deployed and reachable over HTTPS (`DEPLOY.md`), with its address
   written down. Call it `https://api.pedagogue.app` below.
2. An Apple Developer Program membership and the app created in App Store Connect
   with bundle ID `com.pedagogue.app` (`MOBILE_RELEASE.md`, section 3).
3. A Google Play developer account and the app created in Play Console with
   package name `com.pedagogue.app` (`MOBILE_RELEASE.md`, section 4).
4. This version of the app built once and uploaded: a TestFlight build for iOS, and
   an App Bundle in a Play **Internal testing** release for Android. Google will not
   let you create subscriptions until a build that includes the billing permission
   has been uploaded, and this version is the first that does (the RevenueCat plugin
   adds it).
5. Accounts for **paid apps**:
   - Apple: App Store Connect > **Business** (older consoles: Agreements, Tax, and
     Banking) > accept the **Paid Apps** agreement and fill in your bank account and
     tax forms. Subscriptions cannot be sold or even tested until its status is
     **Active**.
   - Google: Play Console > **Setup > Payments profile**, finish your merchant
     account (name, address, bank). 

## Step 1. Create the RevenueCat account and project

1. Go to <https://app.revenuecat.com/signup> and sign up. RevenueCat is free until
   your tracked revenue passes its threshold, which is far above a new app's.
2. Create a project named `Pedagogue`.
3. Open **Project settings > General**. Under what happens when a purchase is
   restored on a different account, choose **Keep with original App User ID**.
   Pedagogue's backend ignores RevenueCat's `TRANSFER` event, so this setting is what
   keeps each store subscription on the one Pedagogue account that bought it.

## Step 2. Connect the App Store to RevenueCat

You do this in the browser on your PC.

1. In RevenueCat, **Project settings > Apps > + New**, choose **App Store**.
   App name `Pedagogue iOS`, bundle ID `com.pedagogue.app`.
2. RevenueCat asks for an **In-App Purchase Key**. Create it in App Store Connect:
   **Users and Access > Integrations > In-App Purchase > Generate In-App Purchase
   Key** (the key's name can be `RevenueCat`). Download the `.p8` file once (Apple
   shows it only once), and note the **Key ID** and **Issuer ID** shown on that page.
3. Back in RevenueCat, upload the `.p8` file and enter the Key ID and Issuer ID,
   then **Save**.
4. Optional, but it saves typing: in the same RevenueCat page add an **App Store
   Connect API key** (from **Users and Access > Integrations > App Store Connect
   API**, role **App Manager**) so RevenueCat can import your products.
5. Still on the App Store app page, find **App Store server notifications** and copy
   the URL RevenueCat shows. In App Store Connect open your app > **App Information
   > App Store Server Notifications** and paste it into both the **Production** and
   **Sandbox** URL boxes (Version 2). This is how refunds and cancellations reach
   RevenueCat quickly.
6. Copy the app's **Public API key**. It starts with `appl_`. You will use it in
   step 6.

## Step 3. Connect Google Play to RevenueCat

1. In RevenueCat, **Project settings > Apps > + New**, choose **Play Store**.
   App name `Pedagogue Android`, package name `com.pedagogue.app`.
2. RevenueCat needs a Google **service account** to read your subscriptions. Follow
   the guide it links ("Creating a service account") in the Google Cloud console:
   - Create (or pick) a Google Cloud project. In **APIs and services > Library**,
     enable the **Google Play Android Developer API** and the **Google Play
     Developer Reporting API**.
   - **IAM and admin > Service accounts > Create service account**, named
     `revenuecat`. Create a **JSON key** for it and download the file.
   - In Play Console go to **Users and permissions > Invite new users**, enter the
     service account's email address, and give it these app permissions for
     Pedagogue: **View app information and download bulk reports (read-only)**,
     **View financial data, orders, and cancellation survey responses**, and
     **Manage orders and subscriptions**. Google can take up to a day or so to start
     honouring a new service account.
3. Upload the JSON key to RevenueCat on the Play Store app page and **Save**.
4. On the same page RevenueCat offers to set up **Google developer notifications**
   (the Pub/Sub topic that tells RevenueCat about renewals and cancellations). Press
   its setup button, then in Play Console open your app > **Monetize with Play >
   Monetization setup** > **Real-time developer notifications**, paste the topic
   name RevenueCat shows, and save. Use **Send test notification** to confirm.
5. Copy the app's **Public API key**. It starts with `goog_`.

## Step 4. Create the two subscriptions in App Store Connect

1. App Store Connect > **Apps > Pedagogue > Monetization > Subscriptions** (older
   console: the app's **Subscriptions** tab). Under **Subscription Groups** choose
   **Create**, with the reference name `Pedagogue Pro`.
2. Add the monthly subscription:
   - **Reference Name** `Pedagogue Pro Monthly`.
   - **Product ID** `pedagogue_pro_monthly`. Apple never lets you reuse or change
     it, so type it carefully.
   - **Subscription Duration**: 1 Month.
3. Add the yearly subscription the same way: reference name `Pedagogue Pro Yearly`,
   product ID `pedagogue_pro_yearly`, duration 1 Year. Put it in the same group, and
   in the group's **Ranking** put yearly above monthly (higher level). Moving up is
   then an upgrade, and moving down waits for the end of the paid period.
4. For each subscription:
   - **Subscription Prices**: add your price, then let Apple fill in the other
     countries.
   - **Introductory Offers**: **Create Introductory Offer**, countries **All**, start
     date today, type **Free**, duration **1 week** (7 days), eligibility **New
     Subscribers**.
   - **App Store Localization**: add English with a display name (`Pedagogue Pro`)
     and a short description (`Unlimited pieces, PDF score reading, full keyboard
     history, share cards and cloud sync.`).
   - **Review Information**: a screenshot of the app's Pro upgrade screen
     (`Settings > Plan > See Pro`) and a note such as "Sign in with the demo account
     and open Settings, then Plan."
5. Under the **Subscription Group** open **App Store Localization** too and give the
   group a name shown to customers: `Pedagogue Pro`.
6. Each product should reach the state **Ready to Submit**. Apple reviews the first
   subscriptions together with a new app version: on the version's page, scroll to
   **In-App Purchases and Subscriptions**, press **+**, and add both before you
   submit for review (`MOBILE_RELEASE.md`, section 10).
7. Terms of Use: Apple requires a link to them. In the app's **Description** add
   `Terms of Use: https://pedagogue.app/terms` and keep `Privacy Policy:
   https://pedagogue.app/privacy`. The app itself already shows both links under the
   prices.

## Step 5. Create the two subscriptions in Google Play Console

1. Play Console > Pedagogue > **Monetize with Play > Products > Subscriptions >
   Create subscription**.
2. Monthly:
   - **Product ID** `pedagogue_pro_monthly` (permanent), **Name** `Pedagogue Pro
     Monthly`, **Description** the same one-line benefits as on Apple.
   - **Add a base plan**: **Base plan ID** `monthly`, type **Auto-renewing**,
     **Billing period** Monthly, set the price and **Update prices** for the other
     countries, grace period and account hold left on, **Save** and **Activate**.
   - On the base plan choose **Add offer**: **Offer ID** `free-trial`, eligibility
     **New customer acquisition** (people who never had this subscription), then
     **Add phase** > **Free trial**, duration **1 week**. **Activate** the offer.
3. Yearly: the same again with product ID `pedagogue_pro_yearly`, base plan ID
   `yearly`, billing period **Yearly**, and a `free-trial` offer of 1 week.
4. Make sure every product shows **Active**.

## Step 6. Wire up RevenueCat

1. **Products**: RevenueCat > your project > **Product catalog > Products**. Press
   **+ New** (or **Import products** after connecting the App Store Connect API key
   and the Play service account). Add `pedagogue_pro_monthly` and
   `pedagogue_pro_yearly` for the App Store app, and `pedagogue_pro_monthly:monthly`
   and `pedagogue_pro_yearly:yearly` for the Play Store app. A product shows
   **Approved** or **Ready to submit** once the store knows it.
2. **Entitlements**: **Product catalog > Entitlements > + New**, identifier `pro`.
   Open it and **Attach** all four products.
3. **Offerings**: **Product catalog > Offerings**. Open `default` (or create it), mark
   it **Current**, and add two packages:
   - **Monthly** (identifier `$rc_monthly`) with the monthly product of each store
   - **Annual** (identifier `$rc_annual`) with the yearly product of each store

   The apps look for exactly these two package types, so use the built-in Monthly
   and Annual rather than custom ones.
4. **Public SDK keys**: **Project settings > API keys**. Copy the `appl_...` key for
   the App Store app and the `goog_...` key for the Play Store app. They are public
   keys that ship inside the apps, so they are safe in the build settings. Never
   use the secret key (`sk_...`) anywhere in this project.

## Step 7. Tell the backend about RevenueCat

1. Make a long random shared secret. In PowerShell:

   ```powershell
   $bytes = New-Object byte[] 32
   [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
   -join ($bytes | ForEach-Object { $_.ToString("x2") })
   ```

   Copy the 64 characters it prints.
2. Render > `pedagogue-api` > **Environment**: add `REVENUECAT_WEBHOOK_SECRET` with
   that value. `REVENUECAT_ENTITLEMENT_ID` is already `pro` in the blueprint; change
   it only if you named the entitlement something else. Save, and let it redeploy.
3. RevenueCat > **Project settings > Integrations > Webhooks > + New**:
   - **Webhook URL** `https://api.pedagogue.app/api/v1/billing/revenuecat/webhook`
   - **Authorization header value**: the same secret (RevenueCat sends it as the
     `Authorization` header, and the backend accepts it with or without a `Bearer `
     prefix)
   - **Environment**: send both **Production** and **Sandbox**
   - **Events**: all events, for all apps
4. Press **Send test event**. RevenueCat should show a `200` response. (The backend
   answers `{"received": true, "outcome": "ignored"}` to a test event. A `401` means
   the secret doesn't match, and a `503` means `REVENUECAT_WEBHOOK_SECRET` isn't set
   on the API yet.)

### What each RevenueCat event does

| Event | Pro afterwards |
|---|---|
| `INITIAL_PURCHASE`, `RENEWAL`, `PRODUCT_CHANGE`, `UNCANCELLATION`, `REFUND_REVERSED`, `SUBSCRIPTION_EXTENDED`, `TEMPORARY_ENTITLEMENT_GRANT` | Yes. A free-trial purchase is `trialing`, and the trial counts as used. |
| `CANCELLATION` (the customer turned renewal off) | Yes until the paid period ends, and Settings says "It won't renew." |
| `CANCELLATION` with reason `CUSTOMER_SUPPORT` (a refund) | No, straight away |
| `BILLING_ISSUE` | Yes while the store retries the card, like Stripe's `past_due`; Settings warns them |
| `EXPIRATION` | No |

`TEST`, `TRANSFER`, `SUBSCRIPTION_PAUSED` and the other events are acknowledged and
ignored. If a renewal event is ever lost, Pro stops 3 days after the stored period
end, the same grace as Stripe. Each event is handled once, events older than what is
stored are ignored, and events for an entitlement other than `pro` are ignored.

If someone has Pro from two places (the website and a store), the one that is not
holding Pro can't switch it off: a store expiry doesn't cancel a live Stripe plan,
and the other way round. When one of them ends, the other carries on.

## Step 8. Put the public keys into the app builds

The apps read the keys from build settings, and only start RevenueCat inside the
native apps. The website ignores them.

- **Codemagic**: open the app > **Environment variables**, group `pedagogue_web`
  (the same group as `VITE_API_URL`), and add
  - `VITE_REVENUECAT_IOS_API_KEY` = the `appl_...` key
  - `VITE_REVENUECAT_ANDROID_API_KEY` = the `goog_...` key

  They don't need the Secret tick. Start a new build afterwards, because the keys
  are baked in at build time.
- **On your PC** (to build the Android app locally): copy `frontend\.env.example` to
  `frontend\.env` and fill in the same two values.

If a key is empty, that app builds and runs normally but sells nothing, as before.

## Step 9. Sandbox testers

Test purchases never charge real money and never reach real customers' revenue.

### iPhone: a sandbox Apple account

1. App Store Connect > **Users and Access > Sandbox > Test Accounts** (older
   console: **Users and Access > Sandbox Testers**) > **+**.
2. Fill in a first name, last name, a **new email address that is not an Apple ID**
   (a Gmail alias such as `you+sandbox1@gmail.com` works if the inbox is yours), a
   password, a country that matches a country your subscriptions are sold in, and
   save. You don't need to verify the email.
3. On the iPhone you will use for testing, nothing needs changing in Settings yet.
   When the purchase sheet appears you are asked to sign in; use the sandbox account
   there. (If the phone is signed in with your real Apple ID, that is fine.) On iOS 16
   and later you can also set it at **Settings > Developer > Sandbox Apple Account**
   once a TestFlight or development build is installed.
4. Purchases made from a TestFlight build are always in the sandbox. Apple shortens
   time so you can see renewals quickly:

   | Real length | In the sandbox |
   |---|---|
   | 7-day free trial | 3 minutes |
   | 1 month | 5 minutes |
   | 1 year | 1 hour |

   A sandbox subscription renews a handful of times and then expires on its own.

### Android: license testers

1. Play Console (the account home, not an app) > **Settings > License testing**. Add
   the Gmail addresses of the Google accounts on your test phones. Set **License
   response** to `RESPOND_NORMALLY`. License testers pay nothing; the purchase sheet
   says it is a test card.
2. Open your app > **Testing > Internal testing > Testers**, create an email list
   containing the same addresses, and tick it. Copy the **opt-in link**.
3. On the Android phone, signed in with that Google account, open the opt-in link,
   press **Become a tester**, then install the app from the Play Store link it
   shows. Billing only works for an app installed through Google Play, not for a
   file you copied onto the phone.
4. Test subscriptions renew faster:

   | Real length | For license testers |
   |---|---|
   | 7-day free trial | 3 minutes |
   | 1 month | 5 minutes |
   | 1 year | 30 minutes |

   They renew up to 6 times and then expire.

## Step 10. Test a purchase on each platform

Before you start, check that `https://api.pedagogue.app/health` answers, that the
RevenueCat webhook test returned `200`, and that the build you installed was made
after you set the two `VITE_REVENUECAT_*` keys. You also need a Pedagogue account
that isn't Pro (make a new one in the app).

### iPhone (via TestFlight)

1. Run the **iOS to TestFlight** workflow in Codemagic (`MOBILE_RELEASE.md`, 6a).
   Install the build from the TestFlight app on the iPhone.
2. Create a new account in the app, then open **Settings > Plan > See Pro**.
3. You should see **Monthly** and **Yearly** with the App Store's prices, "Save …%"
   on the yearly, and **Start 7-day free trial** on both. If nothing shows, see
   "When something goes wrong" below.
4. Choose a plan. The App Store sheet says **[Environment: Sandbox]**; confirm with
   the sandbox account's password.
5. Within a few seconds the app says "Welcome to Pro" and Settings shows "Your free
   trial of Pro runs until …".
6. Check both ends: in RevenueCat **Customers**, open the newest customer. Its
   **App User ID** is the Pedagogue user id (a UUID such as
   `6f1c0b52-2d3e-4a47-9b8a-0a1f6f6f0e11`, the `id` of the account in the `users`
   table), and the sandbox purchase is listed under it; in the Webhooks page see the event delivered with a `200`; in Render
   > `pedagogue-api` > **Logs** look for `revenuecat INITIAL_PURCHASE for user … is
   now trialing`.
7. Wait about 3 minutes for the trial to convert and the renewal event to arrive,
   then 5 more for the first monthly renewal. Settings changes from the trial text to
   "Pro, monthly, renewing on …".
8. Cancel: on the iPhone open **Settings > your name > Subscriptions** (sandbox
   accounts appear under **Settings > App Store > Sandbox Account > Manage**), cancel
   Pedagogue Pro, and watch Settings say "It won't renew". When the sandbox period
   runs out, the `EXPIRATION` event arrives and the account goes back to Free.
9. Restore: delete the app, reinstall it from TestFlight, sign in as the same
   account, and press **Restore purchases** on the Pro screen or in Settings > Plan.

### Android phone (via Play Internal testing)

1. Run the **Android to Google Play closed testing** workflow in Codemagic, or
   upload the App Bundle from the **Android App Bundle** workflow to the Internal
   testing track by hand (`MOBILE_RELEASE.md`, 6b), and install it through the
   tester opt-in link from step 9.
2. Create a new account, then **Settings > Plan > See Pro**. You should see both plans
   with Google Play's prices and the trial.
3. Choose a plan. The Google Play sheet shows a test card note; confirm.
4. Check "Welcome to Pro", RevenueCat **Customers**, the webhook delivery and the
   Render log exactly as for iPhone.
5. Cancel in the Play Store app > your profile > **Payments & subscriptions >
   Subscriptions**, and see "It won't renew". For a refund, in Play Console open
   **Orders** (Order management), find the test order and **Refund**; the account goes
   back to Free within a minute (`CANCELLATION` with reason `CUSTOMER_SUPPORT`).
6. Restore: uninstall and reinstall, sign in, press **Restore purchases**.

### One account, every platform

Sign in on the website with the account that bought Pro in the app, and open
**Settings**: it says Pro, and the Free limits are gone. The reverse also holds: buy
Pro on the website with Stripe's test card, sign in on the phone, and the app is Pro
with no purchase screen to go through. **Settings > Plan** says "You have Pro." For
a website subscription the app offers no manage button (change or cancel it on the
website), and for a store subscription the website says it was bought in the App
Store or Google Play and has to be managed there.

## When something goes wrong

| What you see | What to check |
|---|---|
| The app's Pro screen shows only "Your plan" with no prices | The build has no `VITE_REVENUECAT_*` key for that platform (rebuild after setting it), or RevenueCat refused to start (wrong key type: it must be the public `appl_` or `goog_` key). |
| The Pro screen says "Pro isn't open for sign-up yet" in the app | RevenueCat started but returned no plans: the **Current** offering has no Monthly and Annual packages, or the products aren't **Ready to submit** or **Active** in the store. |
| The prices don't appear on iPhone but do on Android | The Paid Apps agreement is not **Active**, or the products are still **Missing Metadata** (add the localization, price and review screenshot). |
| The purchase works but the app never becomes Pro | RevenueCat > Webhooks shows the delivery. `401`: the secret differs between RevenueCat and `REVENUECAT_WEBHOOK_SECRET`. `503`: the secret isn't set on the API. `200` with outcome `unknown user`: the purchase was made while signed out or with another account id, so sign in and press **Restore purchases**. Outcome `ignored`: the product isn't attached to the `pro` entitlement. |
| The sandbox renews but Pro stays "trialing" | The renewal event hasn't been sent yet. Sandbox events can take a minute or two. |
| "Cannot connect to iTunes Store" or "Item unavailable" on Android | The phone isn't signed in as a license tester, the app wasn't installed from Play, or the build's version code is older than the one on the Internal testing track. |
| A tester is charged for real | They're not on the License testing list (Android) or not using a sandbox account (iOS: only TestFlight and development builds use the sandbox). |
| Someone deleted their account but is still being charged | Deleting a Pedagogue account does not cancel a store subscription; only the customer can, in their App Store or Google Play subscriptions. The delete screen warns anyone with a store subscription to cancel it first. |

## Going live

- Apple: add both subscriptions to the app version before you submit it, and
  paste the review notes in `MOBILE_RELEASE.md` section 10a (they now mention the
  subscription). Make sure the subscription **Review Information** screenshot is set.
- Google: promote the build from the closed test to production, with both
  subscriptions **Active**.
- Update the **App Privacy** and **Data safety** forms for purchases
  (`MOBILE_RELEASE.md`, section 8). RevenueCat receives the Pedagogue account id and
  the purchase record.
- Check the App Store and Play listings don't promise anything the Free plan hides
  and don't link to Stripe or a donation page. The apps themselves never do.
- Switch nothing else in RevenueCat: production and sandbox purchases go through the
  same project, the same keys and the same webhook.

## Environment variables

Every variable this adds is described in `DEPLOY.md`.

| Variable | Where | What |
|---|---|---|
| `REVENUECAT_WEBHOOK_SECRET` | `pedagogue-api` | Shared secret the webhook checks. Empty makes the webhook answer 503. |
| `REVENUECAT_ENTITLEMENT_ID` | `pedagogue-api` | The entitlement that means Pro. Default `pro`. |
| `VITE_REVENUECAT_IOS_API_KEY` | Codemagic `pedagogue_web`, `frontend\.env` | Public `appl_...` SDK key. |
| `VITE_REVENUECAT_ANDROID_API_KEY` | Codemagic `pedagogue_web`, `frontend\.env` | Public `goog_...` SDK key. |
