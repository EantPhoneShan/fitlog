# FitLog: step-by-step guide for beginners

This guide assumes you have never used a terminal or AWS before. Every step says what to click
or type. The examples are for **Windows**; where a Mac is different, it says so.

---

## Part 0: Your data, in plain words

### Where does my data go?

That depends on where the app runs. You choose:

| | **On your laptop** (Part 1) | **On AWS** (Parts 2–5) |
|---|---|---|
| Where the records are saved | One file on your laptop: `fitness-app/data/fitness.db` | A database (DynamoDB) in **your own** AWS account, in Singapore |
| Uses your laptop storage? | Yes, but tiny: a year of logs is about 100 KB, ten years about 1 MB (one photo is ~3 MB) | No. Nothing is stored on your phone or laptop |
| Open it from your phone? | No, only on that laptop | Yes, from anywhere, like a normal app |
| Cost | $0 forever, no card | $0 (details below), card needed only to verify who you are |
| If the laptop breaks | Records are lost unless you downloaded a backup | Records are safe in the cloud |

### Is it public?

The **app** is public: anyone with the link can open it and create their own account.
Each person's **records are private**: you only ever see your own log, and nobody else can see yours.

- Everyone logs in with email + password. Passwords are never stored, only a scrambled "hash" of them.
- Until you're ready to publish, set an **invite code** (Part 5). Then only people you give the
  code to can create an account. When you publish, remove the code and anyone can sign up.
- The records sit in a database inside your AWS account. Nobody can read it directly except you,
  signed in to AWS.

### Phone and computer

FitLog is a web app that can be **installed** (this kind of app is called a PWA):
- **Android:** open the link in Chrome → menu ⋮ → **Install app** / **Add to Home screen**.
- **iPhone:** open the link in Safari → Share button → **Add to Home Screen**.
- **Computer:** open the link in Chrome or Edge → install icon at the right end of the address bar.

It then gets its own icon and opens full-screen like a normal app. The same account works
everywhere: log on your phone at the gym and see it on your laptop at home.

### Backups

In the app go to **Me → Backup → Download backup**. You get one small file with every record.
Put it in Google Drive once a month. **Restore from file** puts it back, on the laptop version or
the AWS version. That is also how you move your log from one to the other.

### Can AWS really cost $0? (the honest answer)

Since July 2025, a new AWS account picks one of two plans when you sign up:

- **Free plan** (pick this one). AWS **cannot charge you**: you get $100–$200 of free credits, and if
  they run out the account closes instead of billing you. The catch: the Free plan lasts
  **6 months**. After that the account closes unless you upgrade. Your data is kept for 90 more days,
  so you can still upgrade or download a backup.
- **Paid plan.** No 6-month limit. Some services are "always free" up to a monthly limit, and FitLog
  only uses those:
  - Lambda (runs the app): 1,000,000 requests a month free. You will use maybe 3,000.
  - DynamoDB (the database): 25 GB free. You will use under 1 MB.

  So even on the Paid plan your bill should stay **$0.00**. FitLog also sets up an email alarm that
  warns you if the bill ever passes $0.50.

**Recommended path:** start on the **Free plan** now: zero risk, and you learn AWS. Around month 5,
decide:
- upgrade to the Paid plan (it should still be $0, and the alarm watches it), or
- download a backup and go back to running FitLog on your laptop.

AWS asks for a **debit or credit card at sign-up even for the Free plan**. It's only to check you're a
real person, and your bank may show a temporary $1 check that disappears. If you can't use a card,
stay with Part 1 (laptop). It's free forever and you can move to AWS later with a backup.

---

## Part 1: Run FitLog on your laptop

### 1.1 Install Python
1. Go to **python.org → Downloads** and download **Python 3.13** (any 3.13.x).
2. Run the installer. On the first screen, **tick "Add python.exe to PATH"** (very important), then
   click **Install Now**.
3. Mac: run the installer; nothing to tick.

### 1.2 Get the app files
1. Download `fitness-app.zip` from our chat.
2. Right-click it → **Extract All** → put it in `Documents`. You now have `Documents\fitness-app`.

### 1.3 Open a terminal in that folder
- **Windows:** open the `fitness-app` folder in File Explorer, click the address bar, type
  `powershell` and press **Enter**. A blue/black window opens. That's the terminal.
- **Mac:** open **Terminal**, type `cd ` (with a space), drag the `fitness-app` folder into the
  window, press **Enter**.

### 1.4 Install the app's libraries (one time)
Type each line and press **Enter** after it:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Mac: use `python3 -m venv .venv` and `source .venv/bin/activate` instead of the first two lines.

- If Windows says *"running scripts is disabled"*, run
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, type `Y`, then try `Activate.ps1` again.
- When it works, the line starts with `(.venv)`.

### 1.5 Start the app
```powershell
cd src
uvicorn app.main:app --reload
```
Open your browser at **http://127.0.0.1:8000**. That's FitLog.
To stop it, click the terminal and press **Ctrl + C**.

**Next time** you only need: open the terminal in `fitness-app` →
`.venv\Scripts\Activate.ps1` → `cd src` → `uvicorn app.main:app --reload`.

---

## Part 2: Create your AWS account (Free plan)

1. Go to **aws.amazon.com** → **Create an AWS Account**.
2. Enter your email and an account name (e.g. `adam-cloud`). Verify the code they email you.
   Choose a strong password.
3. When asked for a plan, choose **Free plan**.
4. Contact info: choose **Personal**.
5. Enter your card (identity check only on the Free plan).
6. Verify your phone number by SMS.
7. Support plan: **Basic support – Free**.
8. Sign in to the **AWS Console**. Top right, next to your name, change the region to
   **Asia Pacific (Singapore) ap-southeast-1**.

### 2.1 Protect the account (5 minutes, don't skip)
1. Top right, click your account name → **Security credentials**.
2. Under **Multi-factor authentication (MFA)**, click **Assign MFA device**. Choose **Authenticator app**,
   scan the QR code with Google Authenticator or Microsoft Authenticator, and enter two codes.

### 2.2 Make a day-to-day user (so you don't use the main "root" login)
1. In the top search bar, type **IAM** and open it.
2. **Users → Create user**. User name: `adam-dev`.
3. Tick **Provide user access to the AWS Management Console** → **I want to create an IAM user** →
   choose **Custom password** → untick "must create a new password". Click **Next**.
4. Choose **Attach policies directly**. Search and tick **AdministratorAccess**, then search and tick
   **SignInLocalDevelopmentAccess**. Click **Next → Create user**.
5. Copy the **Console sign-in URL** shown. Bookmark it.
6. Sign out, open that URL, and sign in as `adam-dev`. Use this user from now on.

---

## Part 3: Install the AWS tools on your laptop

1. **AWS CLI**: search "install AWS CLI v2". Download the Windows MSI (or the macOS pkg) from
   docs.aws.amazon.com and install it.
2. **AWS SAM CLI**: search "install AWS SAM CLI". Download the Windows MSI (or macOS pkg) and install it.
3. **Close and reopen** the terminal, then check both:

```powershell
aws --version
sam --version
```
`aws` must say **2.32 or newer**. If it's older, install the CLI again.

---

## Part 4: Connect your laptop to your AWS account

### 4.1 Log in
```powershell
aws login --profile fitlog-login
```
- When it asks **AWS Region**, type `ap-southeast-1` and press **Enter**.
- Your browser opens. Choose the `adam-dev` session, then go back to the terminal.
  It says you're logged in.

### 4.2 One-time settings so the SAM tool can use that login
Open the AWS settings file:
- Windows: `notepad $HOME\.aws\config`
- Mac: `open -e ~/.aws/config`

Add these lines at the bottom, then save and close:

```ini
[profile fitlog]
credential_process = aws configure export-credentials --profile fitlog-login --format process
region = ap-southeast-1
```

Test it:
```powershell
aws sts get-caller-identity --profile fitlog
```
If you see your account number and `adam-dev`, it works.

The login lasts 12 hours. Another day, just run `aws login --profile fitlog-login` again.

---

## Part 5: Put FitLog on AWS

In the terminal, go to the `fitness-app` folder (not `src`):

```powershell
sam build
```
It ends with **Build Succeeded**. If it complains about the Python version, make sure
`python --version` says 3.13.

**Step 0: make your secret key.** It signs everyone's log-ins. Run:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
Copy the long text it prints and save it somewhere safe (a note on your phone). Use the **same**
key every time you deploy, or everyone gets logged out.

```powershell
sam deploy --guided --profile fitlog
```
It asks questions. Answer like this:

| Question | Type |
|---|---|
| Stack Name | `fitlog` |
| AWS Region | `ap-southeast-1` |
| Parameter SecretKey | the long random text from step 0 below (it won't show while you type) |
| Parameter SignupCode | an invite code, e.g. `gym-2026` (only people with it can sign up; leave empty when you publish) |
| Parameter AlertEmail | your email |
| Confirm changes before deploy | `y` |
| Allow SAM CLI IAM role creation | `y` |
| Disable rollback | `n` |
| FitLogFunction Function Url has no authentication. Is this okay? | `y` (the app has its own log-in) |
| Save arguments to configuration file | `y` |
| SAM configuration file / environment | just press **Enter** |

When it shows the list of changes and asks **Deploy this changeset?**, type `y`.
After 2–4 minutes you see **Outputs** with **AppUrl**, a link ending in `.lambda-url.ap-southeast-1.on.aws/`.

1. Open that link on your phone. Tap **Create account**, enter your name, email, a password and
   your invite code. (The first account created also gets any records from the older version.)
2. Install it: see "Phone and computer" in Part 0. Now it opens like an app.
3. Check your email and click **Confirm subscription** from AWS Budgets. That's your bill alarm.
4. If you logged days on the laptop version: on the laptop go to **History → Download backup**,
   then on the phone app go to **Me → Restore from file**.

### Updating the app after changing code
```powershell
sam build
sam deploy --profile fitlog
```

### See what you built (good for learning)
In the AWS Console, search:
- **Lambda** → `fitlog`: your code; **Monitor** shows every request.
- **DynamoDB** → Tables → `fitlog-days` → **Explore table items**: your records.
- **CloudFormation** → `fitlog`: everything the template created.
- **Billing and Cost Management**: should say **$0.00**.

### Remove everything
```powershell
sam delete --profile fitlog
```
This deletes the app **and the database**, so download a backup first.

---

## When something goes wrong

| You see | Do this |
|---|---|
| `python` is not recognized | Reinstall Python and tick **Add python.exe to PATH** |
| `aws login` is not a valid choice | Your AWS CLI is too old: reinstall it (needs 2.32+) |
| `ExpiredToken` / `credentials` error | Run `aws login --profile fitlog-login` again |
| The app link says **Forbidden** | Lambda console → `fitlog` → Configuration → Function URL: auth type should be **NONE**; accept the permission it offers to add |
| "Wrong invite code" | Use the SignupCode you typed in Part 5. To change it, run `sam deploy --guided --profile fitlog` again |
| Everyone got logged out | The SecretKey changed. Use the same key you saved in Step 0 every time you deploy |
| Anything else | Copy the red error text into our chat |
