// The contact list. Every row is a backend collision contact; its highlight —
// intrusion (penetrating), imminent (inside the margin), or clear — comes from
// the backend's own signed depth via contactSeverity (CG-G-S12e). The GUI makes
// no collision decision: it reads dist and margin the backend reports and colors
// the row. Intrusion and imminent rows are highlighted; clear rows are not.

import { contactSeverity, SEVERITY_LABELS, type ContactSeverity } from "./contactSeverity";
import type { ContactRecord } from "./source";

interface ContactListProps {
  contacts: readonly ContactRecord[];
}

function severityOf(contact: ContactRecord): ContactSeverity {
  return contactSeverity(contact.distMeters, contact.marginMeters);
}

export function ContactList({ contacts }: ContactListProps) {
  return (
    <section className="oa-safety__panel" aria-labelledby="oa-safety-contact-title">
      <h2 id="oa-safety-contact-title" className="oa-safety__panel-title">
        접촉 · 근접
      </h2>

      {contacts.length === 0 ? (
        <p className="oa-safety__status-line">접촉 없음</p>
      ) : (
        <ul className="oa-contact">
          {contacts.map((contact) => {
            const severity = severityOf(contact);
            return (
              <li
                key={contact.id}
                className={`oa-contact__row oa-contact__row--${severity}`}
                data-contact={contact.id}
                data-severity={severity}
              >
                <span className={`oa-contact__sev oa-contact__sev--${severity}`}>
                  {SEVERITY_LABELS[severity]}
                </span>
                <span className="oa-contact__geoms">
                  {contact.geom1} ↔ {contact.geom2}
                </span>
                <span className="oa-contact__dist">
                  dist {contact.distMeters.toFixed(3)} m
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
