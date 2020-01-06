import sys
IS_V3 = False
if (sys.version_info > (3, 0)):
    IS_V3 = True

import vim
import math
import time
from vimade import highlighter
from vimade import signs
from vimade import colors
from vimade.buf_state import BufState
from vimade.win_state import WinState
from vimade import global_state as GLOBALS

FADE = sys.modules[__name__]
HAS_NVIM_WIN_GET_CONFIG = True if int(vim.eval('exists("*nvim_win_get_config")')) else False

windows = {}
background = ''
prevent = False
currentWin = False
startWin = False
buffers = {}
activeWindow = str(vim.current.window.number)
activeBuffer = str(vim.current.buffer.number)





def update(nextState = None):
  start = time.time()
  if FADE.prevent:
    return

  currentWindows = FADE.windows
  currentBuffers = FADE.buffers

  #Check our globals/settings for changes
  status = GLOBALS.update()

  if status & GLOBALS.DISABLE_SIGNS:
    unfadeAllSigns()
  elif status & GLOBALS.ERROR:
    return
  if status & GLOBALS.RECALCULATE:
    highlighter.recalculate()
    return
  elif status & GLOBALS.FULL_INVALIDATE:
    highlighter.reset()
    for winState in currentWindows.values():
      if winState.faded:
        unfadeWin(winState)
        winState.faded = False
    for bufferState in currentBuffers.values():
      bufferState.coords = {}

    #TODO remove this code when possible
    #Ideally this return would not be necessary, but oni current requires a hard refresh here
    return
  else:
    #this is a pre check to make sure that highlights have not been wiped (for example by colorscheme changes)
    highlighter.pre_check()


  fade = {}
  unfade = {}

  FADE.startWin = FADE.currentWin = vim.eval('win_getid('+str(vim.current.window.number)+')')
  activeBuffer = nextState["activeBuffer"]
  activeWindow = nextState['activeWindow']
  activeTab = nextState['activeTab']
  activeDiff = False
  activeScrollbind = False
  nextWindows = {}
  nextBuffers = {}
  fade_signs = []
  unfade_signs = []
  diffs = []
  scrollbinds = []

  FADE.activeBuffer = activeBuffer

  for window in vim.windows:
    winnr = str(window.number)
    bufnr = str(window.buffer.number)
    tabnr = str(window.tabpage.number)
    if activeTab != tabnr:
      continue
    (winid, diff, wrap, buftype, win_disabled, buf_disabled, vimade_fade_active, scrollbind, win_syntax, buf_syntax) = vim.eval('[win_getid('+winnr+'), gettabwinvar('+tabnr+','+winnr+',"&diff"), gettabwinvar('+tabnr+','+winnr+',"&wrap"), gettabwinvar('+tabnr+','+winnr+',"&buftype"), gettabwinvar('+tabnr+','+winnr+',"vimade_disabled"), getbufvar('+bufnr+', "vimade_disabled"),  g:vimade_fade_active, gettabwinvar('+tabnr+','+winnr+',"&scrollbind"), gettabwinvar('+tabnr+','+winnr+',"current_syntax"), gettabwinvar('+tabnr+','+winnr+',"&syntax")]')
    syntax = win_syntax if win_syntax else buf_syntax
    floating = vim.eval('nvim_win_get_config('+str(winid)+')') if HAS_NVIM_WIN_GET_CONFIG else False
    if floating and 'relative' in floating:
      floating = floating['relative']
    else:
      floating = False


    diff = int(diff)
    wrap = int(wrap)
    scrollbind = int(scrollbind)
    vimade_fade_active = int(vimade_fade_active)
    hasActiveBuffer = False if vimade_fade_active else bufnr == activeBuffer
    hasActiveWindow = False if vimade_fade_active else winid == activeWindow

    # window was unhandled -- add to FADE
    if not bufnr in FADE.buffers:
      FADE.buffers[bufnr] = {}
      bufState = FADE.buffers[bufnr] = BufState(bufnr)
    else:
      bufState = FADE.buffers[bufnr]
      
    
    if not winid in FADE.windows:
      state = FADE.windows[winid] = WinState(winid, window, hasActiveBuffer, hasActiveWindow)
      state.syntax = syntax
    else:
      state = FADE.windows[winid]

    state.win = window
    state.number = winnr
    state.tab = tabnr
    state.diff = diff

    if floating or win_disabled or buf_disabled:
      unfade[winid] = state
      continue

    if syntax != state.syntax:
      state.clear_syntax = state.syntax
      state.syntax = syntax
      if not hasActiveBuffer:
        fade[winid] = state


    state.buftype = buftype

    if state.wrap != wrap:
      state.wrap = wrap
      if not hasActiveWindow:
        fade[winid] = state

    if diff and GLOBALS.group_diff:
      diffs.append(state)
      if hasActiveBuffer:
        activeDiff = True

    if scrollbind and GLOBALS.group_scrollbind:
      scrollbinds.append(state)
      if hasActiveBuffer:
        activeScrollbind = True

    # window state changed
    if (window.height != state.height or window.width != state.width or window.cursor[0] != state.cursor[0] or window.cursor[1] != state.cursor[1]):
      state.height = window.height
      state.width = window.width
      state.cursor = (window.cursor[0], window.cursor[1])
      if not hasActiveBuffer:
        fade[winid] = state
    if state.buffer != bufnr:
      state.buffer = bufnr
    if state.hasActiveBuffer != hasActiveBuffer:
      state.hasActiveBuffer = hasActiveBuffer
      if hasActiveBuffer:
        unfade[winid] = state
      else:
        fade[winid] = state
    if state.hasActiveWindow != hasActiveWindow:
      state.hasActiveWindow = hasActiveWindow

    if state.faded and hasActiveBuffer:
      unfade[winid] = state
    elif not state.faded and not hasActiveBuffer:
      fade[winid] = state

    if 'minimap' in window.buffer.name:
      state.is_minimap = True

      currentBuf = '\n'.join(state.win.buffer)
      #TODO can we add additional buf comparisons and move bufState check out of fadeWin?
      if GLOBALS.fade_minimap:
        if not bufState.faded or currentBuf != bufState.last:
          fade[winid] = state
          if winid in unfade:
            del unfade[winid]
      else:
        unfade[winid] = state
        if winid in fade:
          del fade[winid]

    nextBuffers[bufnr] = nextWindows[winid] = True

  if activeDiff and len(diffs) > 1:
    for state in diffs:
      if state.id in fade:
        del fade[state.id]
      unfade[state.id] = state

  if activeScrollbind and len(scrollbinds) > 1:
    for state in scrollbinds:
      if state.id in fade:
        del fade[state.id]
      unfade[state.id] = state

  for win in fade.values():
    fadeWin(win)
    if not FADE.buffers[win.buffer].faded:
      fade_signs.append(win.buffer)
      FADE.buffers[win.buffer].faded = time.time()
    win.faded = True
  for win in unfade.values():
    if win.faded:
      unfadeWin(win)
      win.faded = False
      if not win.buffer in unfade_signs:
        FADE.buffers[win.buffer].faded = 0
        unfade_signs.append(win.buffer)

  expr = []
  ids = []
  for win in list(FADE.windows.keys()):
    if not win in nextWindows:
      expr.append('win_id2tabwin('+win+')')
      ids.append(win)
  expr = vim.eval('['+','.join(expr)+']')
  i = 0
  for item in expr:
    if item[0] == '0' and item[1] == '0':
      del FADE.windows[ids[i]]
    i += 1


  expr = []
  ids = []
  for key in list(FADE.buffers.keys()):
    if not key in nextBuffers:
      expr.append('win_findbuf('+key+')')
      ids.append(key)
  expr = vim.eval('['+','.join(expr)+ ']')
  i = 0
  for item in expr:
    if len(item) == 0:
      del FADE.buffers[ids[i]]
    i += 1


  if GLOBALS.enable_signs:
    now = time.time()
    signs_retention_period = GLOBALS.signs_retention_period
    for bufnr in nextBuffers:
      if bufnr in buffers:
        buf = buffers[bufnr]
        if buf.faded and buf.faded != True and not bufnr in fade_signs:
            fade_signs.append(bufnr)
            if signs_retention_period != -1 and (now - buf.faded) * 1000 >= signs_retention_period:
              buf.faded = True

    if len(fade_signs) or len(unfade_signs):
      if len(fade_signs):
        signs.fade_bufs(fade_signs)
      signs.unfade_bufs(unfade_signs)
  returnToWin()
  FADE.prevent = False
  # if (time.time() - start) * 1000 > 10:
    # print('update',(time.time() - start) * 1000)

def returnToWin():
  if FADE.currentWin != FADE.startWin:
    vim.command('noautocmd call win_gotoid('+FADE.startWin+')')
    FADE.currentWin = False
    FADE.startWin = False

def unfadeAllSigns():
  currentBuffers = buffers
  bufs = []
  for bufState in currentBuffers.values():
    if bufState.faded:
      bufState.faded = 0
      bufs.append(bufState.bufnr)
  if len(bufs):
    signs.unfade_bufs(bufs)

def unfadeAll():
  FADE.startWin = FADE.currentWin = vim.eval('win_getid('+str(vim.current.window.number)+')')
  currentWindows = windows
  for winState in currentWindows.values():
      if winState.faded:
        winState.faded = False
        unfadeWin(winState)
  unfadeAllSigns()
  returnToWin()

def softInvalidateSigns():
  for buf in FADE.buffers.values():
    if buf.faded:
      buf.faded = time.time()

def softInvalidateBuffer(bufnr):
  currentWindows = windows
  for winState in currentWindows.values():
    if winState.buffer == bufnr and winState.faded == True:
      winState.faded = False

def unfadeWin(winState, clear_syntax = False):
  matches = winState.matches
  winid = str(winState.id)
  if FADE.currentWin != winid:
    FADE.currentWin = winid
    vim.command('noautocmd call win_gotoid('+winid+')')
  syntax = clear_syntax if clear_syntax else winState.syntax
  if syntax in FADE.buffers[winState.buffer].coords:
    coords = FADE.buffers[winState.buffer].coords[syntax]
    errs = 0
    if coords:
      for items in coords:
        if items:
          for item in items:
            if item and winid in item:
              del item[winid]
  if matches:
    to_delete = [] 
    for match in matches:
        to_delete.append('silent! call matchdelete('+match+')')
    try:
      vim.command('|'.join(to_delete))
    except:
      pass
  winState.clear_syntax = False
  winState.matches = []

def fadeWin(winState):
  startTime = time.time()
  win = winState.win
  winid = winState.id
  tabnr = winState.tab
  winnr = winState.number
  width = winState.width
  height = winState.height
  cursor = winState.cursor
  wrap = winState.wrap
  setWin = False
  buf = win.buffer
  cursorCol = cursor[1]
  cursorRow = cursor[0]
  startRow = cursor[0] - height - GLOBALS.row_buf_size
  endRow = cursor[0] +  height + GLOBALS.row_buf_size
  matches = {}
  if winState.is_minimap:
    fade_priority='9'
  else:
    fade_priority = GLOBALS.fade_priority

  to_eval = []

  if FADE.currentWin != winid:
    FADE.currentWin = winid
    vim.command('noautocmd call win_gotoid('+winid+')')
  lookup = vim.eval('winsaveview()')
  startRow = int(lookup['topline'])
  endRow = startRow + height
  startCol = int(lookup['leftcol']) + int(lookup['skipcol']) + 1
  maxCol = startCol + width
  if GLOBALS.enable_scroll and not wrap:
    startRow -= GLOBALS.row_buf_size
    endRow += GLOBALS.row_buf_size
    if startRow < 1:
      startRow = 1
    startCol -= GLOBALS.col_buf_size
    maxCol += GLOBALS.col_buf_size
    if startCol < 1:
      startCol = 1

  row = startRow
  buf_ln = len(buf)
  rows_so_far = 0
  while rows_so_far < height and row <= buf_ln:
    fold = int(vim.eval('foldclosedend('+str(row)+')'))
    if fold > -1:
      row = fold
      rows_so_far += 1
    else:
      text = bytes(buf[row-1], 'utf-8', 'replace') if IS_V3 else buf[row-1]
      text_ln = len(text)
      if wrap:
        if text_ln > width * height and row < cursorRow:
          pass
        else:
          chars_left = (height - rows_so_far) * width
          if row == cursorRow:
            value = startCol + chars_left
            value = value if value < text_ln else text_ln
            to_eval.append((row, startCol, value))
            rows_so_far += math.ceil((value - startCol) / width)
          else:
            value = text_ln if text_ln < chars_left else chars_left 
            to_eval.append((row, 1, chars_left))
            rows_so_far += math.ceil(value / width)
      elif text_ln > 0:
        to_eval.append((row, startCol, maxCol if maxCol < text_ln else text_ln))
        rows_so_far += 1
      else:
        rows_so_far += 1
    row += 1



  bufState = FADE.buffers[winState.buffer]
  if not winState.syntax in bufState.coords:
    bufState.coords[winState.syntax] = None
  coords = bufState.coords[winState.syntax]

  currentBuf = '\n'.join(buf)
  if bufState.last != currentBuf:
    unfadeWin(winState)
    coords = None
    #todo remove all highlights? - negative impact on perf but better sync highlights
  elif winState.clear_syntax:
    unfadeWin(winState, winState.clear_syntax)
    coords = None
  bufState.last = currentBuf 
  if coords == None:
    coords = bufState.coords[winState.syntax] = [None] * len(buf)
  winMatches = winState.matches

  row = startRow
  redo = False
  for z in range(0, len(to_eval)):
    (row, startCol, mCol) = to_eval[z]
    column = startCol
    index = row - 1
    if index >= len(coords) or index < 0:
      continue
    if IS_V3:
      rawText = buf[index]
      text = bytes(rawText, 'utf-8', 'replace')
      text_ln = len(text)
      adjustStart = rawText[0:cursorCol]
      adjustStart = len(bytes(adjustStart, 'utf-8', 'surrogateescape')) - len(adjustStart)
      adjustEnd = rawText[cursorCol:mCol]
      adjustEnd = len(bytes(adjustEnd, 'utf-8', 'surrogateescape')) - len(adjustEnd)
    else:
      text = buf[index]
      text_ln = len(text)
      rawText = text.decode('utf-8')
      adjustStart = rawText[0:cursorCol]
      adjustStart = len(adjustStart.encode('utf-8')) - len(adjustStart)
      adjustEnd = rawText[cursorCol:mCol]
      adjustEnd = len(adjustEnd.encode('utf-8')) - len(adjustEnd)

    column -= adjustStart
    column = max(column, 1)
    endCol = min(mCol + adjustEnd, text_ln)
    colors = coords[index]
    if colors == None:
      colors = coords[index] = [None] * text_ln
    str_row = str(row)


    ids = []
    gaps = []

    sCol = column
    # columns = []
    # while len(columns) < endCol - column and 
    # concealed = []
    # while column <= endCol:
      # concealed.append('synconcealed('+str_row+','+str(column)+')')
      # column = column + 1
    # concealed = vim.eval('[' + ','.join(concealed) + ']')

    column = sCol
    while column <= endCol:
      #get syntax id and cache
      current = colors[column - 1]

      if current == None:
        ids.append('synID('+str_row+','+str(column)+',0)')
        gaps.append(column - 1)
      column = column + 1

    if len(ids):
      ids = vim.eval('[' + ','.join(ids) + ']')
      highlights = highlighter.fade_ids(ids)
      i = 0
      for hi in highlights:
        colors[gaps[i]] = {'id': ids[i], 'hi': hi}
        i += 1
    column = sCol
    while column <= endCol:
      current = colors[column - 1]
      if current and not winid in current:
        hi = current['hi']
        current[winid] = True
        if not hi[0] in matches:
           matches[hi[0]] = [(row, column , 1)]
        else:
          match = matches[hi[0]]
          if match[-1][0] == row and match[-1][1] + match[-1][2] == column:
            match[-1] = (row, match[-1][1], match[-1][2] + 1)
          else:
            match.append((row, column, 1))
      column += 1
    # row = row + 1

  items = matches.items()
  if len(items):
    matchadds = []
    for (group, coords) in matches.items():
      i = 0
      end = len(coords)
      while i < end:
        matchadds.append('matchaddpos("'+group+'",['+','.join(map(lambda tup:'['+str(tup[0])+','+str(tup[1])+','+str(tup[2])+']' , coords[i:i+8]))+'],'+fade_priority+')')
        i += 8
    winState.matches += vim.eval('[' + ','.join(matchadds) + ']')

  # print(str(len(to_eval))+ ' ' + str((time.time() - startTime) * 1000))
