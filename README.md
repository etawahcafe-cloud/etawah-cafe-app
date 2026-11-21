# Etawah Cafe
Android 7+ ग्राहक ऐप और निजी कैफ़े इनबॉक्स। दी गई APK ऑफलाइन अभ्यास के लिए है। असली सरकारी आवेदन की प्रक्रिया कैफ़े संचालक अलग से पूरी करता है।

## Server
Use Python 3.12 and an HTTPS host with a persistent private disk. From server/ run python -m pip install -r requirements.txt. Set the following as private environment variables on the host:
- DATA_DIR = absolute path on the persistent disk. Back up the database and encryption key separately. Define a deletion schedule for completed cases.
- DATA_KEY = output of python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())". Retain the same key across deployments.
- ADMIN_PASSWORD = long random password (16+ characters). Staff username is cafe.
- RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET = merchant account credentials. Start with test mode.
Service fees: income, caste and domicile ₹80 each. New PAN and PAN correction ₹150 each.
- Run gunicorn -w 1 --threads 4 --bind 0.0.0.0:$PORT service:app with PORT supplied by the host. Apply per-client rate limits at the HTTPS proxy. For multiple instances use shared database/storage and a shared rate-limit store.
- Staff view is /staff. Applicants see their application reference and payment status on the same device. Run flask --app service reconcile periodically with the same configuration to refresh payments even when customers do not return. If gateway access fails, rerun. For an expired unpaid link, confirm the old link cannot receive payments before starting a fresh application.
- Before accepting customers, set the document checklist, privacy notice, retention period, service terms and operator contact for your shop. Confirm a real-device test-mode application arrives in /staff with the correct files and amount, then verify the paid status. Change to live credentials when ready.

## Android build
Set ORIGIN in android/Main.java to the HTTPS server origin, without a path or trailing slash. Empty ORIGIN loads the packaged offline practice form. For customer distribution use your own signing key and a release version; uninstall the preview if its signature differs.
Use Android SDK Platform 35, Build Tools 35 and a JDK. Set ANDROID_JAR, TOOLS, STORE, ALIAS and STORE_PASS in a private environment. Run android/build.sh to produce the signed APK. The store password and key password should match for this script. Keep signing material for updates. No credentials belong in the APK.

## Mobile sign-in
Configure a six-digit SMS service in Twilio Verify and set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_VERIFY_SERVICE_SID on the server. Confirm SMS delivery to your Indian mobile number before release. Live endpoints require provider approval and an HTTPS session cookie. The packaged offline preview shows its own practice code locally.
