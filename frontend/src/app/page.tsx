import Navbar from '@/components/Navbar';
import Link from 'next/link';
import styles from './page.module.css';

export default function Home() {
  return (
    <>
      <Navbar />
      
      <main className={styles.main}>
        {/* Hero Section */}
        <section className={styles.hero}>
          <div className={styles.heroContent}>
            <h1 className={styles.headline}>
              Your AI-powered<br />
              <span className="gradient-text">Financial Analyst.</span>
            </h1>
            <p className={styles.subhead}>
              Upload your financial data and get instant analysis, automated charts, 
              and actionable insights — powered by advanced AI that understands the numbers.
            </p>
            <div className={styles.heroActions}>
              <Link href="/signup" className={styles.heroPrimaryBtn}>
                Start analyzing →
              </Link>
              <Link href="#features" className={styles.heroSecondaryBtn}>
                See how it works
              </Link>
            </div>
          </div>

          {/* Animated preview card */}
          <div className={styles.heroPreview}>
            <div className={styles.previewCard}>
              <div className={styles.previewHeader}>
                <div className={styles.previewDots}>
                  <span /><span /><span />
                </div>
                <span className={styles.previewTitle}>CFOBuddy Chat</span>
              </div>
              <div className={styles.previewBody}>
                <div className={styles.previewMsg}>
                  <div className={styles.previewAvatar}>✦</div>
                  <div className={styles.previewText}>
                    Ask me anything about your financial data — revenue trends, cash flow, 
                    variance analysis, or market comparisons. I can generate charts automatically.
                  </div>
                </div>
                <div className={styles.previewChart}>
                  <div className={styles.chartBar} style={{ height: '40%', animationDelay: '0s' }} />
                  <div className={styles.chartBar} style={{ height: '65%', animationDelay: '0.1s' }} />
                  <div className={styles.chartBar} style={{ height: '50%', animationDelay: '0.2s' }} />
                  <div className={styles.chartBar} style={{ height: '80%', animationDelay: '0.3s' }} />
                  <div className={styles.chartBar} style={{ height: '60%', animationDelay: '0.4s' }} />
                  <div className={styles.chartBar} style={{ height: '95%', animationDelay: '0.5s' }} />
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="features" className={styles.section}>
          <div className={styles.sectionHead}>
            <h2 className={styles.sectionTitle}>Everything you need for financial clarity.</h2>
            <p className={styles.sectionDesc}>
              CFOBuddy combines AI reasoning with your data to deliver the insights your business needs.
            </p>
          </div>

          <div className={styles.grid}>
            {[
              { title: 'Conversational analysis', icon: '💬', desc: 'Ask questions in plain English. CFOBuddy understands context, interprets financial data, and provides detailed explanations.' },
              { title: 'Automated charts', icon: '📊', desc: 'Generate beautiful, interactive visualizations from your data — revenue trends, cash flow waterfalls, and more.' },
              { title: 'Multi-format support', icon: '📁', desc: 'Upload PDF, XLSX, CSV, or DOCX files. CFOBuddy indexes and understands your documents automatically.' },
              { title: 'Real-time market data', icon: '📈', desc: 'Get live stock prices, market trends, and financial metrics integrated directly into your analysis.' }
            ].map((feat, i) => (
              <div key={i} className={styles.featureCard}>
                <div className={styles.featureIcon}>{feat.icon}</div>
                <h3 className={styles.featureTitle}>{feat.title}</h3>
                <p className={styles.featureDesc}>{feat.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className={styles.ctaSection}>
          <div className={styles.ctaInner}>
            <h2>Ready to understand your finances better?</h2>
            <p>Start analyzing your financial data with AI — upload a file and ask anything.</p>
            <Link href="/dashboard" className={styles.heroPrimaryBtn}>
              Start now →
            </Link>
          </div>
        </section>
      </main>

      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <div className={styles.footerBrand}>
            <span style={{ color: '#10a37f', marginRight: 6 }}>✦</span>
            <span style={{ fontWeight: 700 }}>CFOBuddy</span>
          </div>
          <p className={styles.copyright}>© {new Date().getFullYear()} CFOBuddy. All rights reserved.</p>
          <div className={styles.footerLinks}>
            <a href="#">Privacy</a>
            <a href="#">Terms</a>
            <a href="#">Security</a>
            <a href="#">Contact</a>
          </div>
        </div>
      </footer>
    </>
  );
}
