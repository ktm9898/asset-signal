/**
 * Google Apps Script - Dynamic Asset Allocation & Portfolio Signals Engine
 * Repository: ktm9898/asset-signal
 */

function getAuthPin() {
  const pin = PropertiesService.getScriptProperties().getProperty("AUTH_PIN");
  return pin ? String(pin).trim() : "";
}

function setupSheets() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // 1. Portfolio Signals Sheet (실시간 시그널 & 리밸런싱 지시서 히스토리)
  let sigSheet = ss.getSheetByName("Portfolio_Signals") || ss.insertSheet("Portfolio_Signals");
  sigSheet.getRange("A1:J1").setValues([[
    "Date", "Benchmark", "BenchmarkPrice", "BenchmarkATH", "BenchmarkMDD", 
    "CurrentState", "TargetWeights", "DeltaWeights", "Advice", "UpdatedAt"
  ]]);
  sigSheet.getRange("A1:J1").setFontWeight("bold").setBackground("#e0f2fe");

  // 2. Strategy Slots Sheet (1~10번 전략 슬롯 설정 저장)
  let slotsSheet = ss.getSheetByName("Strategy_Slots") || ss.insertSheet("Strategy_Slots");
  slotsSheet.getRange("A1:M1").setValues([[
    "SlotID", "Name", "Memo", "Benchmark", "BaseWeights", 
    "DropStages", "RecoveryStages", "GainThresholdPct", "ToleranceBandPct", 
    "CooldownDays", "FeeRate", "UpdatedAt", "IsActive"
  ]]);
  slotsSheet.getRange("A1:M1").setFontWeight("bold").setBackground("#dbeafe");

  // 3. Execution Logs Sheet (일일 봇 실행 로그)
  let logSheet = ss.getSheetByName("Execution_Logs") || ss.insertSheet("Execution_Logs");
  logSheet.getRange("A1:E1").setValues([["Timestamp", "Status", "BenchmarkMDD", "CurrentState", "Message"]]);
  logSheet.getRange("A1:E1").setFontWeight("bold").setBackground("#dcfce7");
}

function doGet(e) {
  const inputPin = e.parameter.pin ? String(e.parameter.pin).trim() : "";
  const authPin = getAuthPin();
  const action = e.parameter.action || "all";
  const ss = SpreadsheetApp.getActiveSpreadsheet();

  // 0. Dedicated PIN Verification Action
  if (action === "verify_pin") {
    if (!authPin) {
      return ContentService.createTextOutput(JSON.stringify({ success: true, pinRequired: false, valid: true, message: "No PIN configured" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    if (inputPin === authPin) {
      return ContentService.createTextOutput(JSON.stringify({ success: true, pinRequired: true, valid: true, message: "PIN verified" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    return ContentService.createTextOutput(JSON.stringify({ success: false, pinRequired: true, valid: false, message: "Invalid PIN" }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // 0.5 On-Demand Fetch Ticker History from Yahoo Finance (public)
  if (action === "fetch_ticker_history") {
    const ticker = String(e.parameter.ticker || "").trim().toUpperCase();
    if (!ticker) {
      return ContentService.createTextOutput(JSON.stringify({ success: false, message: "No ticker provided" }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    try {
      const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(ticker)}?range=15y&interval=1d`;
      const resp = UrlFetchApp.fetch(url, {
        headers: { "User-Agent": "Mozilla/5.0" },
        muteHttpExceptions: true
      });
      
      if (resp.getResponseCode() === 200) {
        const json = JSON.parse(resp.getContentText());
        const chart = json.chart && json.chart.result && json.chart.result[0];
        if (chart && chart.timestamp) {
          const timestamps = chart.timestamp;
          const quotes = chart.indicators.quote[0];
          const adjcloseObj = chart.indicators.adjclose && chart.indicators.adjclose[0];
          const adjclose = adjcloseObj ? adjcloseObj.adjclose : quotes.close;
          
          const dates = [];
          const closePrices = [];
          const adjClosePrices = [];
          
          for (let i = 0; i < timestamps.length; i++) {
            if (quotes.close[i] !== null && quotes.close[i] !== undefined) {
              const d = new Date(timestamps[i] * 1000);
              const dateStr = Utilities.formatDate(d, "GMT", "yyyy-MM-dd");
              dates.push(dateStr);
              closePrices.push(Number(quotes.close[i].toFixed(2)));
              adjClosePrices.push(adjclose && adjclose[i] !== null ? Number(adjclose[i].toFixed(2)) : Number(quotes.close[i].toFixed(2)));
            }
          }
          
          return ContentService.createTextOutput(JSON.stringify({
            success: true,
            ticker: ticker,
            name: (chart.meta && (chart.meta.shortName || chart.meta.symbol)) || ticker,
            dates: dates,
            close: closePrices,
            adjClose: adjClosePrices,
            latestPrice: closePrices[closePrices.length - 1] || 0
          })).setMimeType(ContentService.MimeType.JSON);
        }
      }
      return ContentService.createTextOutput(JSON.stringify({ success: false, message: "Ticker not found on Yahoo Finance" }))
        .setMimeType(ContentService.MimeType.JSON);
    } catch (err) {
      return ContentService.createTextOutput(JSON.stringify({ success: false, message: err.toString() }))
        .setMimeType(ContentService.MimeType.JSON);
    }
  }

  // 1. PIN Authorization Check for Protected Endpoints
  if (authPin && inputPin !== authPin) {
    return ContentService.createTextOutput(JSON.stringify({ 
      success: false, 
      status: "error", 
      pinRequired: true, 
      message: "Unauthorized: Invalid PIN" 
    })).setMimeType(ContentService.MimeType.JSON);
  }

  // 2. Set Active Strategy Slot
  if (action === "set_active_strategy_slot") {
    const slotId = parseInt(e.parameter.slotId || "1", 10);
    PropertiesService.getScriptProperties().setProperty("ACTIVE_STRATEGY_SLOT_ID", String(slotId));
    
    setupSheets();
    const sheet = ss.getSheetByName("Strategy_Slots");
    if (sheet && sheet.getLastRow() > 1) {
      const lastRow = sheet.getLastRow();
      const lastCol = sheet.getLastColumn();
      const activeFlags = [];
      for (let i = 2; i <= lastRow; i++) {
        const rowId = parseInt(sheet.getRange(i, 1).getValue(), 10);
        activeFlags.push([rowId === slotId ? "적용중 (ACTIVE)" : ""]);
      }
      sheet.getRange(2, lastCol, activeFlags.length, 1).setValues(activeFlags);
    }

    return ContentService.createTextOutput(JSON.stringify({ success: true, status: "success", activeSlotId: slotId }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // 2.5 Set Rebalance Date
  if (action === "set_rebalance_date") {
    const dateVal = String(e.parameter.date || "").trim();
    if (dateVal) {
      PropertiesService.getScriptProperties().setProperty("REBALANCE_DATE", dateVal);
    }
    return ContentService.createTextOutput(JSON.stringify({ success: true, status: "success", rebalanceDate: dateVal }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // 3. Get Strategy Slots
  if (action === "get_strategy_slots") {
    setupSheets();
    let slotsSheet = ss.getSheetByName("Strategy_Slots");
    let slots = [];
    if (slotsSheet && slotsSheet.getLastRow() > 1) {
      const rows = slotsSheet.getRange(2, 1, slotsSheet.getLastRow() - 1, slotsSheet.getLastColumn()).getValues();
      slots = rows.map((r, idx) => {
        return {
          id: r[0] || (idx + 1),
          name: r[1] || `전략 ${idx + 1}`,
          memo: r[2] || '',
          benchmark: r[3] || 'QQQ',
          baseWeights: r[4] ? parseJsonSafe(r[4], {"QQQ": 0.6, "SCHD": 0.4}) : {"QQQ": 0.6, "SCHD": 0.4},
          dropStages: r[5] ? parseJsonSafe(r[5], []) : [],
          recoveryStages: r[6] ? parseJsonSafe(r[6], []) : [],
          gainThresholdPct: r[7] !== '' && r[7] !== null ? Number(r[7]) : 20.0,
          toleranceBandPct: r[8] !== '' && r[8] !== null ? Number(r[8]) : 5.0,
          cooldownDays: r[9] !== '' && r[9] !== null ? Number(r[9]) : 5,
          feeRate: r[10] !== '' && r[10] !== null ? Number(r[10]) : 0.001,
          updatedAt: r[11] || '-',
          isActive: String(r[12] || '').includes('적용') || String(r[12] || '').includes('ACTIVE'),
          isEmpty: (r[1] && String(r[1]).includes('비어있음')) || !r[4]
        };
      });
    }
    
    const activeSlotId = PropertiesService.getScriptProperties().getProperty("ACTIVE_STRATEGY_SLOT_ID") || "1";
    const rebalanceDate = PropertiesService.getScriptProperties().getProperty("REBALANCE_DATE") || "2024-01-02";
    return ContentService.createTextOutput(JSON.stringify({ 
      success: true, 
      slots: slots, 
      activeSlotId: parseInt(activeSlotId, 10),
      rebalanceDate: rebalanceDate 
    })).setMimeType(ContentService.MimeType.JSON);
  }

  // 4. PIN Authorization Check for Protected Endpoints
  if (authPin && inputPin !== authPin && action !== "holdings") {
    return ContentService.createTextOutput(JSON.stringify({ success: false, status: "error", message: "Unauthorized: Invalid PIN" }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  // 5. Default Query (all, signals, holdings, logs)
  setupSheets();
  let result = { success: true, status: "success" };

  if (action === "all" || action === "signals" || action === "portfolio_signals") {
    result.portfolioSignals = getSheetData(ss.getSheetByName("Portfolio_Signals"));
  }
  if (action === "all" || action === "holdings" || action === "portfolio_holdings") {
    result.portfolioHoldings = getSheetData(ss.getSheetByName("Portfolio_Holdings"));
  }
  if (action === "all" || action === "logs") {
    result.executionLogs = getSheetData(ss.getSheetByName("Execution_Logs"));
  }

  const activeSlotId = PropertiesService.getScriptProperties().getProperty("ACTIVE_STRATEGY_SLOT_ID") || "1";
  const rebalanceDate = PropertiesService.getScriptProperties().getProperty("REBALANCE_DATE") || "2024-01-02";
  result.activeSlotId = parseInt(activeSlotId, 10);
  result.rebalanceDate = rebalanceDate;

  return ContentService.createTextOutput(JSON.stringify(result)).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const authPin = getAuthPin();
    const inputPin = (data.pin || "").toString().trim();

    // 0. PIN Authorization Check for POST
    if (authPin && inputPin !== authPin) {
      return ContentService.createTextOutput(JSON.stringify({ 
        success: false, 
        status: "error", 
        pinRequired: true, 
        message: "Unauthorized: Invalid PIN" 
      })).setMimeType(ContentService.MimeType.JSON);
    }

    // 1. Set Active Strategy Slot
    if (data.action === "set_active_strategy_slot") {
      const slotId = parseInt(data.slotId || "1", 10);
      PropertiesService.getScriptProperties().setProperty("ACTIVE_STRATEGY_SLOT_ID", String(slotId));
      
      setupSheets();
      const sheet = ss.getSheetByName("Strategy_Slots");
      if (sheet && sheet.getLastRow() > 1) {
        const lastRow = sheet.getLastRow();
        const lastCol = sheet.getLastColumn();
        const activeFlags = [];
        for (let i = 2; i <= lastRow; i++) {
          const rowId = parseInt(sheet.getRange(i, 1).getValue(), 10);
          activeFlags.push([rowId === slotId ? "적용중 (ACTIVE)" : ""]);
        }
        sheet.getRange(2, lastCol, activeFlags.length, 1).setValues(activeFlags);
      }

      return ContentService.createTextOutput(JSON.stringify({ success: true, status: "success", activeSlotId: slotId }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 1.5 Set Rebalance Date
    if (data.action === "set_rebalance_date") {
      const dateVal = String(data.date || "").trim();
      if (dateVal) {
        PropertiesService.getScriptProperties().setProperty("REBALANCE_DATE", dateVal);
      }
      return ContentService.createTextOutput(JSON.stringify({ success: true, status: "success", rebalanceDate: dateVal }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 2. Save Strategy Slots
    if (data.action === "save_strategy_slots") {
      setupSheets();
      const sheet = ss.getSheetByName("Strategy_Slots");
      const slots = data.slots || [];
      const activeSlotId = parseInt(data.activeSlotId || PropertiesService.getScriptProperties().getProperty("ACTIVE_STRATEGY_SLOT_ID") || "1", 10);
      
      if (slots.length > 0) {
        if (sheet.getLastRow() > 1) {
          sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).clearContent();
        }
        const nowStr = Utilities.formatDate(new Date(), "GMT+9", "yyyy-MM-dd HH:mm:ss");
        const rows = slots.map((s, idx) => {
          const slotId = s.id || (idx + 1);
          const isActive = (slotId === activeSlotId);
          return [
            slotId,
            s.name || `전략 ${slotId}`,
            s.memo || '',
            s.benchmark || 'QQQ',
            JSON.stringify(s.baseWeights || {}),
            JSON.stringify(s.dropStages || []),
            JSON.stringify(s.recoveryStages || []),
            s.gainThresholdPct !== undefined ? s.gainThresholdPct : 20.0,
            s.toleranceBandPct !== undefined ? s.toleranceBandPct : 5.0,
            s.cooldownDays !== undefined ? s.cooldownDays : 5,
            s.feeRate !== undefined ? s.feeRate : 0.001,
            nowStr,
            isActive ? "적용중 (ACTIVE)" : ""
          ];
        });
        sheet.getRange(2, 1, rows.length, 13).setValues(rows);
        PropertiesService.getScriptProperties().setProperty("ACTIVE_STRATEGY_SLOT_ID", String(activeSlotId));
      }

      return ContentService.createTextOutput(JSON.stringify({ success: true, status: "success", count: slots.length }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 3. Update Portfolio Signal (Called by Python Screener)
    if (data.action === "update_portfolio_signal") {
      setupSheets();
      const sheet = ss.getSheetByName("Portfolio_Signals");
      const sig = data.signal || {};
      const nowStr = Utilities.formatDate(new Date(), "GMT+9", "yyyy-MM-dd HH:mm:ss");
      
      let prevState = "";
      if (sheet.getLastRow() > 1) {
        prevState = String(sheet.getRange(2, 6).getValue() || "").trim();
        sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).clearContent();
      }
      
      const curState = String(sig.currentState || "기본 (정상 운용)").trim();
      const hasDelta = sig.deltaWeights && Object.keys(sig.deltaWeights).length > 0;
      const isStateChanged = prevState && prevState !== curState;
      const isSpecialState = !curState.includes("평시") && !curState.includes("정상");

      sheet.getRange(2, 1, 1, 10).setValues([[
        sig.date || Utilities.formatDate(new Date(), "GMT+9", "yyyy-MM-dd"),
        sig.benchmark || "QQQ",
        sig.benchmarkPrice || 0,
        sig.benchmarkATH || 0,
        sig.benchmarkMDD || 0,
        curState,
        JSON.stringify(sig.targetWeights || {}),
        JSON.stringify(sig.deltaWeights || {}),
        sig.advice || "",
        nowStr
      ]]);

      // Only append to Execution_Logs when an actual signal/rebalance occurs (state change or drop stage entered)
      if (isStateChanged || isSpecialState || hasDelta) {
        const logSheet = ss.getSheetByName("Execution_Logs");
        logSheet.appendRow([
          nowStr,
          "신호발생",
          sig.benchmarkMDD || 0,
          curState,
          sig.advice || "포트폴리오 리밸런싱 신호 발생"
        ]);
      }

      return ContentService.createTextOutput(JSON.stringify({ success: true, status: "success" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 4. Update / Add / Delete Portfolio Holdings
    if (data.action === "add_portfolio_holding" || data.action === "add_user_holding") {
      setupSheets();
      const sheet = ss.getSheetByName("Portfolio_Holdings");
      const today = Utilities.formatDate(new Date(), "GMT+9", "yyyy-MM-dd");
      sheet.appendRow([
        today,
        String(data.ticker || "").trim().toUpperCase(),
        data.name || data.ticker,
        data.quantity || 0,
        data.buyPrice || 0,
        data.currentPrice || data.buyPrice || 0,
        data.currentWeightPct || 0,
        data.targetWeightPct || 0,
        data.deltaPct || 0,
        data.currency || "USD",
        data.notes || ""
      ]);
      return ContentService.createTextOutput(JSON.stringify({ success: true, status: "success" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    if (data.action === "delete_portfolio_holding" || data.action === "delete_user_holding") {
      const sheet = ss.getSheetByName("Portfolio_Holdings");
      if (sheet && sheet.getLastRow() > 1) {
        const target = String(data.ticker || "").trim().toUpperCase();
        const dataRows = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getValues();
        for (let i = dataRows.length - 1; i >= 0; i--) {
          const rowTicker = String(dataRows[i][1] || "").trim().toUpperCase();
          if (rowTicker === target) {
            sheet.deleteRow(i + 2);
          }
        }
      }
      return ContentService.createTextOutput(JSON.stringify({ success: true, status: "success" }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // 5. Trigger GitHub Actions (Screener)
    if (data.action === "trigger_screener") {
      if (data.slotId) {
        PropertiesService.getScriptProperties().setProperty("ACTIVE_STRATEGY_SLOT_ID", String(data.slotId));
      }
      const githubToken = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
      if (!githubToken) {
        return ContentService.createTextOutput(JSON.stringify({ 
          success: false, 
          status: "error", 
          message: "구글 앱스 스크립트에 GITHUB_TOKEN 이 설정되어 있지 않습니다. Script Properties에 GITHUB_TOKEN을 추가해주세요." 
        })).setMimeType(ContentService.MimeType.JSON);
      }

      const url = "https://api.github.com/repos/ktm9898/asset-signal/actions/workflows/screener.yml/dispatches";
      const options = {
        method: "post",
        contentType: "application/json",
        headers: {
          "Accept": "application/vnd.github+json",
          "User-Agent": "GoogleAppsScript",
          "Authorization": "Bearer " + githubToken.trim()
        },
        payload: JSON.stringify({ ref: "main" }),
        muteHttpExceptions: true
      };
      
      try {
        const resp = UrlFetchApp.fetch(url, options);
        const code = resp.getResponseCode();
        if (code === 204 || code === 200) {
          return ContentService.createTextOutput(JSON.stringify({ success: true, status: "success", message: "포트폴리오 신호 산출이 GitHub Actions 서버에서 시작되었습니다." }))
            .setMimeType(ContentService.MimeType.JSON);
        } else {
          return ContentService.createTextOutput(JSON.stringify({ 
            success: false, 
            status: "error", 
            message: "깃허브 API 오류 (HTTP " + code + "): " + resp.getContentText() 
          })).setMimeType(ContentService.MimeType.JSON);
        }
      } catch (err) {
        return ContentService.createTextOutput(JSON.stringify({ success: false, status: "error", message: "통신 오류: " + err.toString() }))
          .setMimeType(ContentService.MimeType.JSON);
      }
    }

    // 6. Trigger GitHub Actions (Update Backtest Data)
    if (data.action === "trigger_backtest_update") {
      const githubToken = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
      if (!githubToken) {
        return ContentService.createTextOutput(JSON.stringify({ 
          success: false, 
          status: "error", 
          message: "구글 앱스 스크립트에 GITHUB_TOKEN 이 설정되어 있지 않습니다." 
        })).setMimeType(ContentService.MimeType.JSON);
      }

      const url = "https://api.github.com/repos/ktm9898/asset-signal/actions/workflows/update_backtest.yml/dispatches";
      const options = {
        method: "post",
        contentType: "application/json",
        headers: {
          "Accept": "application/vnd.github+json",
          "User-Agent": "GoogleAppsScript",
          "Authorization": "Bearer " + githubToken.trim()
        },
        payload: JSON.stringify({ ref: "main" }),
        muteHttpExceptions: true
      };
      
      try {
        const resp = UrlFetchApp.fetch(url, options);
        const code = resp.getResponseCode();
        if (code === 204 || code === 200) {
          return ContentService.createTextOutput(JSON.stringify({ success: true, status: "success", message: "ETF 백테스트 데이터 갱신이 깃허브 클라우드에서 시작되었습니다." }))
            .setMimeType(ContentService.MimeType.JSON);
        } else {
          return ContentService.createTextOutput(JSON.stringify({ 
            success: false, 
            status: "error", 
            message: "깃허브 API 오류 (HTTP " + code + "): " + resp.getContentText() 
          })).setMimeType(ContentService.MimeType.JSON);
        }
      } catch (err) {
        return ContentService.createTextOutput(JSON.stringify({ success: false, status: "error", message: "통신 오류: " + err.toString() }))
          .setMimeType(ContentService.MimeType.JSON);
      }
    }

    return ContentService.createTextOutput(JSON.stringify({ success: false, status: "error", message: "Unknown action" }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ success: false, status: "error", message: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function getSheetData(sheet) {
  if (!sheet || sheet.getLastRow() <= 1) return [];
  const rows = sheet.getDataRange().getValues();
  const headers = rows[0];
  const data = [];
  for (let i = 1; i < rows.length; i++) {
    let rowObj = {};
    for (let j = 0; j < headers.length; j++) {
      const key = String(headers[j] || "").trim();
      if (!key) continue;
      let val = rows[i][j];
      if (val instanceof Date) {
        val = Utilities.formatDate(val, "GMT+9", "yyyy-MM-dd HH:mm:ss");
      }
      rowObj[key] = val;
    }
    data.push(rowObj);
  }
  return data;
}

function parseJsonSafe(str, fallback) {
  if (!str) return fallback;
  try {
    return JSON.parse(str);
  } catch (e) {
    return fallback;
  }
}

/**
 * Automatically triggered by Google Apps Script UI Triggers (⏰ 트리거)
 */
function triggerGitHubScreener() {
  const githubToken = PropertiesService.getScriptProperties().getProperty("GITHUB_TOKEN");
  const url = "https://api.github.com/repos/ktm9898/asset-signal/actions/workflows/screener.yml/dispatches";
  const options = {
    method: "post",
    contentType: "application/json",
    headers: {
      "Accept": "application/vnd.github+json",
      "User-Agent": "GoogleAppsScript"
    },
    payload: JSON.stringify({ ref: "main" }),
    muteHttpExceptions: true
  };
  if (githubToken) {
    options.headers["Authorization"] = "Bearer " + githubToken;
  }
  try {
    UrlFetchApp.fetch(url, options);
  } catch (err) {}
}
