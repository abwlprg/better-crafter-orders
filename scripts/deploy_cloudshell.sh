#!/bin/bash
# Correr este script desde Cloud Shell:
#   bash scripts/deploy_cloudshell.sh

gcloud run deploy order-app \
  --source . \
  --project ordersbc-494213 \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --update-env-vars MS_CLIENT_ID=61c787fc-4991-49b4-a14c-bd14117ebdfd \
  --update-env-vars MS_TENANT_ID=consumers \
  --update-env-vars ONEDRIVE_FILE_ID='9F9C6569035A2B06!s8f3f59c58ae4411c9bb2622519f7ee43' \
  --update-env-vars ONEDRIVE_DRIVE_ID=9f9c6569035a2b06 \
  --update-env-vars 'MS_REFRESH_TOKEN=M.C561_SN1.0.U.-CvwAyXO7uoHc!ZRXXNO*PhRx6fAbVNJDsLSuxgEc3DvLpOLT!m7fqvXP54JqVMXerm8!MT6rCqfvfHxmeKBcFxiQJ!c7dMszsWo9w26CnwUcpPdSuqKuDpyDIJESfOXHwaBbXWB8FkFgosgfTzaxGTMYmUuJx!h!1S6hCX*Aj7mFjLn3JksNfvkLVPdD!nUTcbA4L!nqJZD9spsi8AQqf!XAKFoP285XFqT8jssBdZAERhAKUha*V28GN4kM*0FLkL*iRPp2vwlKtxXg7GxHYiLxhqeIx61K35FrNdLhAAUguAa58gTKfdf5x1!EGFTUHLAgTFnQbhdX*1!GNgTzjGe!HsnLLaRP3640ave1I6IW'
