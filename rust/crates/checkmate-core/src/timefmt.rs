//! Mise en forme des dates ISO produites par Python, sans dependance ni
//! horloge. Les dates de l'API sont locales et sans fuseau.

/// Date et heure deja analysees, sans fuseau.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LocalStamp {
    pub year: i32,
    pub month: u8,
    pub day: u8,
    pub hour: u8,
    pub minute: u8,
    pub second: u8,
}

impl LocalStamp {
    /// Analyse une date ISO `AAAA-MM-JJTHH:MM:SS`, avec secondes
    /// optionnelles et suffixe `Z` ou decalage ignore.
    pub fn parse(value: &str) -> Option<Self> {
        let text = value.trim();
        if text.len() < 16 {
            return None;
        }
        let (date, rest) = text.split_once('T')?;
        let mut date_parts = date.split('-');
        let year = date_parts.next()?.parse().ok()?;
        let month = date_parts.next()?.parse().ok()?;
        let day = date_parts.next()?.parse().ok()?;
        if date_parts.next().is_some() {
            return None;
        }
        let time = rest
            .split(['Z', '+'])
            .next()
            .unwrap_or(rest)
            .trim_end_matches('Z');
        let mut time_parts = time.split(':');
        let hour = time_parts.next()?.parse().ok()?;
        let minute = time_parts.next()?.parse().ok()?;
        let second = time_parts
            .next()
            .and_then(|item| item.parse().ok())
            .unwrap_or(0);
        if !(1..=12).contains(&month)
            || !(1..=31).contains(&day)
            || hour > 23
            || minute > 59
            || second > 59
        {
            return None;
        }
        Some(Self {
            year,
            month,
            day,
            hour,
            minute,
            second,
        })
    }
}

/// `27/11/2026 a 14:05`, ou la valeur brute si elle n'est pas analysable.
pub fn date_time(value: &str) -> String {
    match LocalStamp::parse(value) {
        Some(stamp) => format!(
            "{:02}/{:02}/{} a {:02}:{:02}",
            stamp.day, stamp.month, stamp.year, stamp.hour, stamp.minute
        ),
        None => value.to_owned(),
    }
}

/// `27/11/2026`, ou la valeur brute si elle n'est pas analysable.
pub fn date(value: &str) -> String {
    match LocalStamp::parse(value) {
        Some(stamp) => format!("{:02}/{:02}/{}", stamp.day, stamp.month, stamp.year),
        None => value.to_owned(),
    }
}

/// Duree lisible : `42 s`, `3 min`, `2 h 05`, `4 j`.
pub fn uptime(seconds: u64) -> String {
    if seconds < 60 {
        return format!("{seconds} s");
    }
    let minutes = seconds / 60;
    if minutes < 60 {
        return format!("{minutes} min");
    }
    let hours = minutes / 60;
    if hours < 24 {
        return format!("{hours} h {:02}", minutes % 60);
    }
    format!("{} j", hours / 24)
}

#[cfg(test)]
mod tests {
    use super::{LocalStamp, date, date_time, uptime};

    #[test]
    fn analyse_une_date_complete() {
        let stamp = LocalStamp::parse("2026-11-27T14:05:09").unwrap();
        assert_eq!(stamp.year, 2026);
        assert_eq!(stamp.hour, 14);
        assert_eq!(stamp.second, 9);
    }

    #[test]
    fn accepte_un_suffixe_de_fuseau() {
        assert_eq!(LocalStamp::parse("2026-11-27T14:05:00Z").unwrap().minute, 5);
        assert_eq!(
            LocalStamp::parse("2026-11-27T14:05:00+01:00").unwrap().hour,
            14
        );
    }

    #[test]
    fn refuse_une_date_invalide() {
        assert!(LocalStamp::parse("hier").is_none());
        assert!(LocalStamp::parse("2026-13-01T00:00:00").is_none());
        assert!(LocalStamp::parse("2026-11-27 14:05").is_none());
    }

    #[test]
    fn affiche_la_date_francaise() {
        assert_eq!(date_time("2026-11-27T14:05:00"), "27/11/2026 a 14:05");
        assert_eq!(date("2026-11-27T14:05:00"), "27/11/2026");
        assert_eq!(date("inconnue"), "inconnue");
    }

    #[test]
    fn affiche_une_duree_courte() {
        assert_eq!(uptime(0), "0 s");
        assert_eq!(uptime(59), "59 s");
        assert_eq!(uptime(60), "1 min");
        assert_eq!(uptime(3_600), "1 h 00");
        assert_eq!(uptime(90_000), "1 j");
    }
}
