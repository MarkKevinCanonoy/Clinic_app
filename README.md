# Clinic_app

## sysrem sa Web hahahaahah


---

## need nga Python Version

atu gamiton na version is ang **Python 3.12**.  
Ang **Python 3.14** dili compatible sa system.  

- pwede ra mag-install ug damo version sa python sa computer.  
- para magamit ang specific version, mag gamit ta ug **virtual environment (venv)**. mag gamit tag virual environment kay aron maka gamit tag lahi na version sa python kay ang default ang latest version man (**3.14**)

**kuan** Sa pag-install sa python, i-check ang **Add Python to PATH**.

---

## pag-setup sa systema ng kadiliman katung naay chatbot

1. adto left side niya naay button ara na naay **main** niya pislita ang **adding-chatbot**
2. copy lang ang link sa kanang <span style="color: green;">Code</span> sa right side kanang green
3. create bago folder
4. e open tong folder sa vscode  
5. if wala pamoy [git](https://git-scm.com/) pag install sa. then after installation open terminal niya
   ```bash
   git clone --> ang link <--
   ```
6. open file explorer niya sulod sa **Clinic_app** na folder. diko sure if pwede ba sa vscode diritso na terminal basta sulod sa **Clinic_app**
   
## mag create tag virtual environment
```bash   
py -3.12 -m venv venv
```
## e activate ang virtual environment:

```bash
venv\Scripts\activate
```

## kung na activate na ang venv, i-install ang mga requirements:

```bash
pip install -r requirements.txt
```

## Pag-human sa installation, i-run ang server:

```bash
python -m uvicorn main:app --reload
```

## if error sa pag run e send lang sa ai ang error niya ingna unsay ipa install haahahahhaahaha yun lang grabe gutoma



   
