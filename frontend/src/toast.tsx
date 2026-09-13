import { createContext, useCallback, useContext, useState } from 'react'

type Toast = { msg: string; err?: boolean } | null
const Ctx = createContext<(msg: string, err?: boolean) => void>(() => {})
export const useToast = () => useContext(Ctx)

export function ToastProvider({ children }: { children: any }) {
  const [t, setT] = useState<Toast>(null)
  const show = useCallback((msg: string, err = false) => {
    setT({ msg, err }); setTimeout(() => setT(null), 3500)
  }, [])
  return (
    <Ctx.Provider value={show}>
      {children}
      {t && <div className={'toast' + (t.err ? ' err' : '')}>{t.msg}</div>}
    </Ctx.Provider>
  )
}
