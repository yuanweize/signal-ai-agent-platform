const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({ args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  const page = await browser.newPage();
  
  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('response', response => {
    if (response.url().includes('/api/')) {
      console.log('API RESPONSE:', response.url(), response.status());
    }
  });

  await page.goto('http://localhost:3000/login');
  
  // Fill form
  await page.type('#username', 'admin');
  await page.type('#password', '3NB7B7BXYN7H6QI5SIOCGDKH5VXABCAF');
  
  // Get TOTP
  const { execSync } = require('child_process');
  const totp = execSync('docker exec smb-backend python3 -c "import pyotp; print(pyotp.TOTP(\'N4TS56IHLBMMR6FYHX4TJ4ACDLDOODXI\').now())"').toString().trim();
  console.log('Using TOTP:', totp);
  
  await page.type('#totp', totp);
  
  // Submit
  await Promise.all([
    page.click('button[type="submit"]'),
    page.waitForNavigation({ waitUntil: 'networkidle0' })
  ]);
  
  console.log('URL after login:', page.url());
  
  await browser.close();
})();
