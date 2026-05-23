export function getIsoWeekStart(input: Date) {
  const date = new Date(input)
  date.setHours(0, 0, 0, 0)
  const day = date.getDay() || 7
  date.setDate(date.getDate() - day + 1)
  return date
}

export function addWeeks(weekStart: Date, amount: number) {
  const date = new Date(weekStart)
  date.setDate(date.getDate() + amount * 7)
  return getIsoWeekStart(date)
}

export function getIsoWeekInfo(weekStart: Date) {
  const target = new Date(Date.UTC(weekStart.getFullYear(), weekStart.getMonth(), weekStart.getDate()))
  const dayNumber = (target.getUTCDay() + 6) % 7
  target.setUTCDate(target.getUTCDate() - dayNumber + 3)
  const year = target.getUTCFullYear()
  const firstThursday = new Date(Date.UTC(year, 0, 4))
  const firstDayNumber = (firstThursday.getUTCDay() + 6) % 7
  firstThursday.setUTCDate(firstThursday.getUTCDate() - firstDayNumber + 3)
  const week = 1 + Math.round((target.getTime() - firstThursday.getTime()) / 604800000)
  return { year, week }
}

export function getWeekKey(weekStart: Date) {
  const { year, week } = getIsoWeekInfo(weekStart)
  return `${year}-W${String(week).padStart(2, "0")}`
}

export function formatWeekRange(weekStart: Date) {
  const end = new Date(weekStart)
  end.setDate(end.getDate() + 6)
  const formatter = new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric" })
  return `${formatter.format(weekStart)} - ${formatter.format(end)}`
}
