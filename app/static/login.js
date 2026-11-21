"use strict";

const loginForm = document.getElementById("login");
const choices = document.getElementById("login-choices");
const tokenField = document.getElementById("login-token-field");
const token = document.getElementById("token");
const submit = document.getElementById("continue");
const feedback = document.getElementById("login-feedback");
const guest = document.getElementById("login-guest");

let mode;
let busy = false;

function showMessage(message) {
  feedback.textContent = message;
  feedback.hidden = !message;
}

function addChoice(account, selected) {
  const label = document.createElement("label");
  label.className = "account-choice";
  const input = document.createElement("input");
  input.type = "radio";
  input.name = "account_id";
  input.value = account.id;
  input.checked = selected;
  const copy = document.createElement("span");
  const name = document.createElement("strong");
  name.textContent = account.name;
  const detail = document.createElement("small");
  detail.textContent = account.detail;
  copy.append(name, detail);
  label.append(input, copy);
  choices.append(label);
}

async function setupLogin() {
  const response = await fetch("/session/options");
  if (!response.ok) throw new Error("暂时无法读取登录选项，请刷新页面重试。");
  const options = await response.json();
  mode = options.mode;
  if (mode === "demo") {
    document.getElementById("login-heading").textContent = "选择演示账号";
    document.getElementById("login-intro").textContent = "选择一个身份即可进入，无需密码。";
    options.accounts.forEach((account, index) => addChoice(account, index === 0));
    choices.hidden = options.accounts.length === 0;
    submit.disabled = options.accounts.length === 0;
    if (submit.disabled) showMessage("本地演示未配置可用账号。");
  } else {
    document.getElementById("login-intro").textContent = "输入服务端为你配置的账号令牌。";
    tokenField.hidden = false;
    token.required = true;
    submit.disabled = false;
  }
}

loginForm.addEventListener("submit", async event => {
  event.preventDefault();
  if (busy || !mode) return;
  const body = mode === "demo"
    ? {account_id: new FormData(loginForm).get("account_id")}
    : {token: token.value.trim()};
  if (!body.account_id && !body.token) {
    showMessage("请选择账号或输入令牌。");
    return;
  }

  busy = true;
  submit.disabled = true;
  showMessage("");
  try {
    const response = await fetch("/session", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(typeof error.detail === "string" ? error.detail : "登录失败，请检查账号。");
    }
    window.location.replace("/");
  } catch (error) {
    showMessage(error.message);
    busy = false;
    submit.disabled = false;
  }
});

guest.addEventListener("click", async event => {
  event.preventDefault();
  if (busy) return;
  busy = true;
  try {
    const response = await fetch("/session", {method: "DELETE"});
    if (!response.ok) throw new Error("暂时无法退出当前账号，请重试。");
    window.location.replace(guest.href);
  } catch (error) {
    showMessage(error.message);
    busy = false;
  }
});

setupLogin().catch(error => showMessage(error.message));
