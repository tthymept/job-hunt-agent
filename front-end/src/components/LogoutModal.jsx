import { clearAccess } from '../api'

// Opened from the name in the sidebar: forgets the access key (or guest view)
// on this device and goes back to the unlock screen
export default function LogoutModal({ guest, onClose }) {
  function logOut() {
    clearAccess()
    window.location.reload()
  }

  return (
    <div className="modal-overlay blocked" onClick={onClose}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <h3>{guest ? 'Leave guest view?' : 'Log out?'}</h3>
        <div className="sub">
          {guest
            ? 'You will go back to the access screen, where you can enter the access key.'
            : 'This device will forget the access key. You will go back to the access screen, where you can enter it again or view as a guest.'}
        </div>
        <div className="modal-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="button" className="btn primary" autoFocus onClick={logOut}>
            {guest ? 'Leave' : 'Log out'}
          </button>
        </div>
      </div>
    </div>
  )
}
